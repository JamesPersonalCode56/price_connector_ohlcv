from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx

from config import SETTINGS
from domain.models import PriceQuote
from infrastructure.common import (
    SubscriptionError,
    WebSocketClientProtocol,
    WebSocketPriceFeedClient,
)

LOGGER = logging.getLogger(__name__)


def _interval_to_seconds(interval: str) -> int:
    if not interval:
        return 60

    text = interval.strip().lower()
    try:
        value = float(text)
    except ValueError:
        value = None

    if value is not None:
        return max(1, int(value * 60))

    magnitude_part: list[str] = []
    unit_part: list[str] = []
    for char in text:
        if char.isdigit() or char == ".":
            magnitude_part.append(char)
        else:
            unit_part.append(char)

    if not magnitude_part:
        return 60

    try:
        magnitude = float("".join(magnitude_part))
    except ValueError:
        return 60

    suffix = (unit_part or ["m"])[0]
    multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}.get(suffix, 60)
    seconds = int(magnitude * multiplier)
    return max(1, seconds)


def _to_epoch_seconds(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric > 1e12:
        numeric /= 1000.0
    return numeric


@dataclass
class GateioClientConfig:
    base_stream_url: str = "wss://api.gateio.ws/ws/v4/"
    channel: str = "spot.candlesticks"
    contract_type: str = "spot"
    interval: str = "1m"


class GateioWebSocketClient(WebSocketPriceFeedClient[GateioClientConfig]):
    exchange = "Gate.io"

    def __init__(self, config: GateioClientConfig) -> None:
        super().__init__(config)
        self._interval_seconds = _interval_to_seconds(config.interval)
        self._rest_client = GateioRestClient(config.contract_type)

    def _build_connection_args(self, symbols: list[str]) -> dict[str, Any]:
        return {"url": self._resolve_stream_url(symbols)}

    async def _on_connected(
        self, ws: WebSocketClientProtocol, symbols: list[str]
    ) -> None:
        subscribe_messages = [
            json.dumps(
                {
                    "time": int(time.time()),
                    "channel": self._config.channel,
                    "event": "subscribe",
                    "payload": [self._config.interval, symbol],
                }
            )
            for symbol in symbols
        ]
        for message in subscribe_messages:
            await ws.send(message)
        endpoint = self._resolve_stream_url(symbols)
        self._logger.info(
            "Subscribed to Gate.io channel",
            extra={
                "channel": self._config.channel,
                "symbols": symbols,
                "interval": self._config.interval,
                "endpoint": endpoint,
            },
        )

    def _inactivity_warning_message(self) -> str:
        return "No Gate.io updates for %.1fs, requesting REST snapshot and reconnecting"

    async def _process_message(
        self,
        message_text: str,
        symbols: list[str],
        ws: WebSocketClientProtocol,
    ) -> list[PriceQuote]:
        message = json.loads(message_text)

        event = message.get("event")
        if event in {"subscribe", "unsubscribe"}:
            return []
        if event == "ping":
            await ws.send(
                json.dumps(
                    {
                        "time": int(time.time()),
                        "channel": message.get("channel", self._config.channel),
                        "event": "pong",
                    }
                )
            )
            return []
        if event != "update":
            return []

        return self._parse_candlestick_result(
            message.get("result"),
            message.get("time"),
            message.get("time_ms"),
        )

    async def _backfill_quotes(self, symbols: list[str]) -> Iterable[PriceQuote]:
        try:
            return await self._rest_client.fetch_latest_candles(
                symbols, self._config.interval
            )
        except Exception as exc:
            self._logger.exception("Failed to fetch Gate.io REST backfill")
            raise SubscriptionError(
                "Gate.io REST backfill failed",
                exchange_message=str(exc),
            ) from exc

    def _resolve_stream_url(self, symbols: list[str]) -> str:
        base_url = self._config.base_stream_url
        if "{settle}" not in base_url:
            return base_url

        settles = {self._extract_settle_currency(symbol) for symbol in symbols}
        settles.discard("")
        if not settles:
            raise ValueError(
                "Unable to determine settle currency for Gate.io delivery stream"
            )
        if len(settles) > 1:
            raise ValueError(
                "Gate.io delivery stream requires symbols with the same settle currency"
            )

        settle = settles.pop()
        return base_url.replace("{settle}", settle)

    @staticmethod
    def _extract_settle_currency(symbol: str) -> str:
        if not isinstance(symbol, str) or "_" not in symbol:
            return ""
        return symbol.split("_", 1)[0].lower()

    def _parse_candlestick_result(
        self,
        result: Any,
        message_time: Any,
        message_time_ms: Any,
    ) -> list[PriceQuote]:
        if result is None:
            return []

        entries: list[dict[str, Any]]
        if isinstance(result, dict):
            entries = [result]
        elif isinstance(result, list):
            if result and all(isinstance(item, dict) for item in result):
                entries = result
            else:
                return []
        else:
            return []

        quotes: list[PriceQuote] = []
        for entry in entries:
            quote = self._build_quote_from_entry(entry, message_time, message_time_ms)
            if quote is not None:
                quotes.append(quote)

        return quotes

    def _build_quote_from_entry(
        self,
        entry: dict[str, Any],
        message_time: Any,
        message_time_ms: Any,
    ) -> PriceQuote | None:
        try:
            open_price = float(entry["o"])
            high_price = float(entry["h"])
            low_price = float(entry["l"])
            close_price = float(entry["c"])
        except (KeyError, TypeError, ValueError):
            return None

        volume = self._to_float(entry.get("a") or entry.get("v"))
        trade_num = self._to_int(entry.get("q"))
        candle_time = entry.get("t")
        timestamp = self._timestamp_from_envelope(message_time_ms, message_time)
        if timestamp is None:
            timestamp = self._resolve_timestamp(
                candle_time, message_time, message_time_ms
            )
        symbol = self._extract_symbol(
            entry.get("currency_pair") or entry.get("contract") or entry.get("n")
        )

        return PriceQuote(
            exchange="gateio",
            symbol=symbol,
            contract_type=self._config.contract_type,
            timestamp=timestamp,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
            trade_num=trade_num,
            is_closed_candle=bool(entry.get("w", False)),
        )

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _to_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _extract_symbol(raw_symbol: Any) -> str:
        if not isinstance(raw_symbol, str):
            return ""
        if raw_symbol and raw_symbol[0].isdigit():
            parts = raw_symbol.split("_", 1)
            if len(parts) == 2:
                return parts[1]
        return raw_symbol

    def _timestamp_from_envelope(
        self, message_time_ms: Any, message_time: Any
    ) -> datetime | None:
        epoch = _to_epoch_seconds(message_time_ms)
        if epoch is None:
            epoch = _to_epoch_seconds(message_time)
        if epoch is None:
            return None
        return datetime.fromtimestamp(epoch, tz=timezone.utc)

    def _resolve_timestamp(
        self, candle_time: Any, message_time: Any, message_time_ms: Any
    ) -> datetime:
        open_epoch = _to_epoch_seconds(candle_time)
        if open_epoch is not None:
            return datetime.fromtimestamp(
                open_epoch + self._interval_seconds, tz=timezone.utc
            )

        for value in (message_time_ms, message_time):
            candidate = _to_epoch_seconds(value)
            if candidate is not None:
                return datetime.fromtimestamp(candidate, tz=timezone.utc)

        return datetime.now(timezone.utc)


class GateioRestClient:
    _ENDPOINTS = {
        "spot": ("https://api.gateio.ws/api/v4/spot/candlesticks", "currency_pair"),
        "um": ("https://api.gateio.ws/api/v4/futures/usdt/candlesticks", "contract"),
        "cm": (
            "https://api.gateio.ws/api/v4/futures/{settle}/candlesticks",
            "contract",
        ),
    }

    def __init__(self, contract_type: str) -> None:
        if contract_type not in self._ENDPOINTS:
            raise ValueError(
                f"Unsupported Gate.io contract_type for REST backfill: {contract_type}"
            )
        self._logger = LOGGER
        self._contract_type = contract_type
        self._base_url, self._symbol_param = self._ENDPOINTS[contract_type]
        self._requires_settle = contract_type == "cm"

    async def fetch_latest_candles(
        self, symbols: Iterable[str], interval: str
    ) -> list[PriceQuote]:
        symbols_list = list(symbols)
        if not symbols_list:
            return []

        interval_seconds = _interval_to_seconds(interval)
        async with httpx.AsyncClient(timeout=SETTINGS.connector.rest_timeout) as client:
            tasks = []
            for symbol in symbols_list:
                base_url = self._resolve_base_url(symbol)
                params: dict[str, str] = {
                    self._symbol_param: symbol,
                    "interval": interval,
                    "limit": "1",
                }
                tasks.append(
                    client.get(
                        base_url,
                        params=params,
                    )
                )
            responses = await asyncio.gather(*tasks, return_exceptions=True)

        candles: list[PriceQuote] = []
        for symbol, response in zip(symbols_list, responses, strict=False):
            if isinstance(response, BaseException):
                extra = {
                    "symbol": symbol,
                    "contract_type": self._contract_type,
                    "error": str(response),
                    "error_type": type(response).__name__,
                }
                if isinstance(response, httpx.TimeoutException):
                    self._logger.warning("Gate.io REST request timed out", extra=extra)
                else:
                    self._logger.warning(
                        "Gate.io REST request failed",
                        extra=extra,
                        exc_info=response if isinstance(response, Exception) else False,
                    )
                continue
            try:
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list) or not payload:
                    continue
                entry_raw = payload[0]
                parsed = self._parse_entry(entry_raw, interval_seconds)
                if parsed is None:
                    continue
                (
                    timestamp,
                    open_price,
                    high_price,
                    low_price,
                    close_price,
                    volume,
                    is_closed,
                ) = parsed

                candles.append(
                    PriceQuote(
                        exchange="gateio",
                        symbol=symbol,
                        contract_type=self._contract_type,
                        timestamp=timestamp,
                        open=open_price,
                        high=high_price,
                        low=low_price,
                        close=close_price,
                        volume=volume,
                        trade_num=0,
                        is_closed_candle=is_closed,
                    )
                )
            except Exception:
                self._logger.warning(
                    "Failed to parse Gate.io REST candle",
                    extra={"symbol": symbol, "contract_type": self._contract_type},
                    exc_info=True,
                )
                continue
        return candles

    @staticmethod
    def _parse_timestamp(raw: Any, interval_seconds: int) -> datetime:
        base = _to_epoch_seconds(raw)
        if base is None:
            return datetime.now(timezone.utc)
        return datetime.fromtimestamp(base + interval_seconds, tz=timezone.utc)

    @staticmethod
    def _parse_entry(
        entry: Any, interval_seconds: int
    ) -> tuple[datetime, float, float, float, float, float, bool] | None:
        if isinstance(entry, list):
            if len(entry) < 7:
                return None
            timestamp_value = entry[0]
            close_price = float(entry[2])
            high_price = float(entry[3])
            low_price = float(entry[4])
            open_price = float(entry[5])
            volume = float(entry[6])
            is_closed = str(entry[7]).lower() == "true" if len(entry) > 7 else True
        elif isinstance(entry, dict):
            try:
                open_price = float(entry["o"])
                high_price = float(entry["h"])
                low_price = float(entry["l"])
                close_price = float(entry["c"])
            except (KeyError, TypeError, ValueError):
                return None
            volume_raw = entry.get("v") or entry.get("volume") or 0
            try:
                volume = float(volume_raw)
            except (TypeError, ValueError):
                volume = 0.0
            is_closed_raw = (
                entry.get("finished")
                or entry.get("completed")
                or entry.get("is_closed")
            )
            is_closed = (
                str(is_closed_raw).lower() == "true"
                if is_closed_raw is not None
                else True
            )
            timestamp_value = (
                entry.get("t") or entry.get("time") or entry.get("timestamp")
            )
        else:
            return None

        timestamp = GateioRestClient._parse_timestamp(timestamp_value, interval_seconds)
        return (
            timestamp,
            open_price,
            high_price,
            low_price,
            close_price,
            volume,
            is_closed,
        )

    def _resolve_base_url(self, symbol: str) -> str:
        if not self._requires_settle:
            return self._base_url
        settle = self._extract_settle_currency(symbol)
        if not settle:
            raise ValueError(
                f"Unable to determine settle currency for Gate.io REST symbol '{symbol}'"
            )
        return self._base_url.format(settle=settle)

    @staticmethod
    def _extract_settle_currency(symbol: str) -> str:
        if not isinstance(symbol, str) or "_" not in symbol:
            return ""
        return symbol.split("_", 1)[0].lower()
