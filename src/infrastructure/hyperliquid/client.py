from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx

from config import SETTINGS
from domain.models import PriceQuote
from infrastructure.common import WebSocketClientProtocol, WebSocketPriceFeedClient


def _to_epoch_ms(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


@dataclass
class HyperliquidWsConfig:
    base_api_url: str = "https://api.hyperliquid.xyz"
    interval: str = "1m"
    market_type: str = "perp"  # "spot" or "perp"
    contract_type: str = "usdm"

    @property
    def stream_url(self) -> str:
        if self.base_api_url.startswith("https://"):
            return "wss://" + self.base_api_url[len("https://") :] + "/ws"
        if self.base_api_url.startswith("http://"):
            return "ws://" + self.base_api_url[len("http://") :] + "/ws"
        return self.base_api_url


class HyperliquidWebSocketClient(WebSocketPriceFeedClient[HyperliquidWsConfig]):
    exchange = "hyperliquid"

    def __init__(self, config: HyperliquidWsConfig) -> None:
        super().__init__(config)
        self._symbol_aliases: dict[str, str] = {}
        base = self._config.base_api_url.rstrip("/")
        self._rest_info_url = f"{base}/info"

    def _build_connection_args(self, symbols: list[str]) -> dict[str, Any]:
        return {"url": self._config.stream_url}

    async def _on_connected(
        self, ws: WebSocketClientProtocol, symbols: list[str]
    ) -> None:
        for symbol in symbols:
            normalized = self._normalize_symbol(symbol)
            subscribe_message = {
                "method": "subscribe",
                "subscription": {
                    "type": "candle",
                    "coin": normalized,
                    "interval": self._config.interval,
                },
            }
            await ws.send(json.dumps(subscribe_message))
            self._symbol_aliases[normalized.upper()] = symbol
            self._logger.info(
                "Subscribed to Hyperliquid candle stream",
                extra={
                    "coin": normalized,
                    "original_symbol": symbol,
                    "interval": self._config.interval,
                    "endpoint": self._config.stream_url,
                },
            )

    async def _process_message(
        self,
        message_text: str,
        symbols: list[str],
        ws: WebSocketClientProtocol,
    ) -> list[PriceQuote]:
        try:
            message = json.loads(message_text)
        except json.JSONDecodeError:
            self._logger.warning(
                "Discarding non-JSON Hyperliquid payload",
                extra={"payload": message_text},
            )
            return []

        channel = message.get("channel")
        if channel != "candle":
            return []

        data = message.get("data")
        if not isinstance(data, dict):
            return []

        quote = self._parse_candle(data)
        return [quote] if quote is not None else []

    async def _backfill_quotes(self, symbols: list[str]) -> Iterable[PriceQuote]:
        if not symbols:
            return []

        interval_ms = self._interval_to_milliseconds(self._config.interval)
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000.0)
        lookback_multiplier = 5
        start_ms = (
            0
            if interval_ms is None
            else max(0, now_ms - interval_ms * lookback_multiplier)
        )

        quotes: list[PriceQuote] = []
        timeout = httpx.Timeout(SETTINGS.connector.rest_timeout)

        async with httpx.AsyncClient(timeout=timeout) as client:
            for original_symbol in symbols:
                coin = self._normalize_symbol(original_symbol)
                payload = {
                    "type": "candleSnapshot",
                    "req": {
                        "coin": coin,
                        "interval": self._config.interval,
                        "startTime": start_ms,
                        "endTime": now_ms,
                    },
                }
                try:
                    response = await client.post(self._rest_info_url, json=payload)
                    response.raise_for_status()
                    candles = response.json()
                except Exception:
                    self._logger.exception(
                        "Hyperliquid REST backfill request failed",
                        extra={"symbol": original_symbol, "payload": payload},
                    )
                    continue

                if not isinstance(candles, list) or not candles:
                    self._logger.debug(
                        "Hyperliquid REST backfill returned no candles",
                        extra={"symbol": original_symbol, "coin": coin},
                    )
                    continue

                candle = candles[-1]
                quote = self._snapshot_to_quote(candle, original_symbol)
                if quote is not None:
                    quotes.append(quote)
                    self._logger.debug(
                        "Hyperliquid REST backfill produced candle",
                        extra={
                            "symbol": original_symbol,
                            "coin": coin,
                            "timestamp": quote.timestamp.isoformat(),
                        },
                    )

        return quotes

    def _normalize_symbol(self, symbol: str) -> str:
        cleaned = symbol.strip()
        if not cleaned:
            raise ValueError("Hyperliquid symbols must be non-empty")

        if self._config.market_type == "spot":
            upper_cleaned = cleaned.upper()
            for separator in ("/", "_", "-"):
                if separator in upper_cleaned:
                    base, quote = upper_cleaned.split(separator, 1)
                    return f"{base}/{quote}"
            raise ValueError(
                "Hyperliquid spot symbols must include a quote currency, e.g. BTC/USDC"
            )

        result = cleaned
        for separator in ("/", "_", ":", "-"):
            if separator in result:
                result = result.split(separator, 1)[0]
                break
        for suffix in ("USDC", "USDT", "USD", "PERP", "SWAP"):
            if result.upper().endswith(suffix) and len(result) > len(suffix):
                result = result[: -len(suffix)]
                break

        return result

    def _snapshot_to_quote(
        self, data: dict[str, Any], symbol: str
    ) -> PriceQuote | None:
        open_epoch = _to_epoch_ms(data.get("t"))
        if open_epoch is None:
            return None

        try:
            open_price = float(data["o"])
            high_price = float(data["h"])
            low_price = float(data["l"])
            close_price = float(data["c"])
        except (KeyError, TypeError, ValueError):
            return None

        volume = _to_float(data.get("v"))
        trade_num = _to_int(data.get("n"))
        open_time = datetime.fromtimestamp(open_epoch / 1000.0, tz=timezone.utc)

        close_epoch = _to_epoch_ms(data.get("T"))
        is_closed = False
        if close_epoch is not None:
            now_epoch = datetime.now(timezone.utc).timestamp() * 1000.0
            is_closed = now_epoch >= close_epoch

        return PriceQuote(
            exchange="hyperliquid",
            symbol=symbol,
            contract_type=self._config.contract_type,
            timestamp=open_time,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
            trade_num=trade_num,
            is_closed_candle=is_closed,
        )

    @staticmethod
    def _interval_to_milliseconds(interval: str) -> int | None:
        if not interval:
            return None
        unit_multipliers = {
            "s": 1_000,
            "m": 60_000,
            "h": 3_600_000,
            "d": 86_400_000,
            "w": 604_800_000,
            "M": 2_592_000_000,  # Approximate month (30 days)
        }
        numeric_part = interval[:-1]
        unit = interval[-1]
        try:
            magnitude = int(numeric_part)
        except ValueError:
            return None
        multiplier = unit_multipliers.get(unit)
        if multiplier is None:
            return None
        return magnitude * multiplier

    def _parse_candle(self, data: dict[str, Any]) -> PriceQuote | None:
        open_epoch = _to_epoch_ms(data.get("t"))
        if open_epoch is None:
            return None

        try:
            open_price = float(data["o"])
            high_price = float(data["h"])
            low_price = float(data["l"])
            close_price = float(data["c"])
        except (KeyError, TypeError, ValueError):
            return None

        volume = _to_float(data.get("v"))
        trade_num = _to_int(data.get("n"))

        symbol_raw = str(data.get("s") or "").upper()
        symbol_display = self._symbol_aliases.get(symbol_raw, data.get("s") or "")

        open_time = datetime.fromtimestamp(open_epoch / 1000.0, tz=timezone.utc)

        close_epoch = _to_epoch_ms(data.get("T"))
        is_closed = False
        if close_epoch is not None:
            now_epoch = datetime.now(timezone.utc).timestamp() * 1000.0
            is_closed = now_epoch >= close_epoch

        return PriceQuote(
            exchange="hyperliquid",
            symbol=symbol_display,
            contract_type=self._config.contract_type,
            timestamp=open_time,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
            trade_num=trade_num,
            is_closed_candle=is_closed,
        )
