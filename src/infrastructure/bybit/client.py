from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, List

import httpx

from config import SETTINGS
from domain.models import PriceQuote
from infrastructure.common import WebSocketClientProtocol, WebSocketPriceFeedClient

LOGGER = logging.getLogger(__name__)


@dataclass
class BybitClientConfig:
    base_stream_url: str
    contract_type: str
    interval: str = "1"


class BybitWebSocketClient(WebSocketPriceFeedClient[BybitClientConfig]):
    exchange = "Bybit"

    def __init__(self, config: BybitClientConfig) -> None:
        super().__init__(config)
        self._rest_client = BybitRestClient(config.contract_type, config.interval)

    def _build_connection_args(self, symbols: list[str]) -> dict[str, Any]:
        return {"url": self._config.base_stream_url}

    async def _on_connected(
        self, ws: WebSocketClientProtocol, symbols: list[str]
    ) -> None:
        topics = [f"kline.{self._config.interval}.{symbol}" for symbol in symbols]
        subscribe_message = json.dumps({"op": "subscribe", "args": topics})
        await ws.send(subscribe_message)
        self._logger.info(
            "Subscribed to Bybit topics",
            extra={"topics": topics, "endpoint": self._config.base_stream_url},
        )

    def _inactivity_warning_message(self) -> str:
        return "No Bybit updates for %.1fs, fetching REST snapshot and reconnecting"

    async def _process_message(
        self,
        message_text: str,
        symbols: list[str],
        ws: WebSocketClientProtocol,
    ) -> list[PriceQuote]:
        message = json.loads(message_text)

        if message.get("op") == "ping":
            await ws.send(json.dumps({"op": "pong"}))
            return []

        topic = message.get("topic", "")
        if not topic.startswith("kline"):
            return []

        data = message.get("data")
        if isinstance(data, dict):
            entries: List[dict[str, Any]] = [data]
        elif isinstance(data, list):
            entries = [entry for entry in data if isinstance(entry, dict)]
        else:
            return []

        stream_timestamp = None
        ts_value = message.get("ts") or message.get("timestamp")
        if ts_value is not None:
            try:
                stream_timestamp = datetime.fromtimestamp(
                    int(ts_value) / 1000, tz=timezone.utc
                )
            except (TypeError, ValueError):
                stream_timestamp = None

        quotes: list[PriceQuote] = []
        for entry in entries:
            try:
                open_price = float(entry["open"])
                high_price = float(entry["high"])
                low_price = float(entry["low"])
                close_price = float(entry["close"])
                volume = float(entry.get("volume", 0.0))
            except (KeyError, TypeError, ValueError):
                continue

            if stream_timestamp is not None:
                timestamp = stream_timestamp
            else:
                end_time = entry.get("end") or entry.get("timestamp") or entry.get("ts")
                if end_time is None:
                    timestamp = datetime.now(timezone.utc)
                else:
                    try:
                        timestamp = datetime.fromtimestamp(
                            int(end_time) / 1000, tz=timezone.utc
                        )
                    except (TypeError, ValueError):
                        timestamp = datetime.now(timezone.utc)

            try:
                trade_num = int(entry.get("tradeNum", 0) or 0)
            except (TypeError, ValueError):
                trade_num = 0

            try:
                symbol = entry.get("symbol") or topic.split(".", 2)[-1]
            except Exception:
                symbol = ""

            quotes.append(
                PriceQuote(
                    exchange="bybit",
                    symbol=symbol,
                    contract_type=self._config.contract_type,
                    timestamp=timestamp,
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=volume,
                    trade_num=trade_num,
                    is_closed_candle=bool(entry.get("confirm", False)),
                )
            )

        return quotes

    async def _backfill_quotes(self, symbols: list[str]) -> Iterable[PriceQuote]:
        try:
            return await self._rest_client.fetch_latest_candles(symbols)
        except Exception:
            self._logger.exception("Failed to fetch Bybit REST backfill")
            return []


class BybitRestClient:
    _BASE_URL = "https://api.bybit.com/v5/market/kline"

    _CATEGORY_ALIASES = {
        "linear": "linear",
        "inverse": "inverse",
        "spot": "spot",
    }

    def __init__(self, contract_type: str, interval: str) -> None:
        category = self._CATEGORY_ALIASES.get(contract_type)
        if category is None:
            raise ValueError(
                f"Unsupported Bybit contract_type for REST backfill: {contract_type}"
            )
        self._logger = LOGGER
        self._category = category
        self._interval = interval
        try:
            self._interval_minutes = int(interval)
        except ValueError:
            self._interval_minutes = 1

    async def fetch_latest_candles(self, symbols: Iterable[str]) -> list[PriceQuote]:
        symbols_list = list(symbols)
        if not symbols_list:
            return []

        async with httpx.AsyncClient(timeout=SETTINGS.connector.rest_timeout) as client:
            tasks = [
                client.get(
                    self._BASE_URL,
                    params={
                        "category": self._category,
                        "symbol": symbol,
                        "interval": self._interval,
                        "limit": "1",
                    },
                )
                for symbol in symbols_list
            ]
            responses = await asyncio.gather(*tasks, return_exceptions=True)

        candles: list[PriceQuote] = []
        for symbol, response in zip(symbols_list, responses, strict=False):
            if isinstance(response, BaseException):
                self._logger.warning(
                    "Bybit REST request failed",
                    extra={"symbol": symbol, "contract_type": self._category},
                    exc_info=isinstance(response, Exception),
                )
                continue
            try:
                response.raise_for_status()
                payload = response.json()
                data = payload.get("result", {}).get("list") or []
                if not data:
                    continue
                candle = data[0]
                start = int(candle[0])
                open_price = float(candle[1])
                high_price = float(candle[2])
                low_price = float(candle[3])
                close_price = float(candle[4])
                volume = float(candle[5])
                timestamp = datetime.fromtimestamp(
                    (start / 1000) + self._interval_minutes * 60,
                    tz=timezone.utc,
                )
                candles.append(
                    PriceQuote(
                        exchange="bybit",
                        symbol=symbol,
                        contract_type=self._category,
                        timestamp=timestamp,
                        open=open_price,
                        high=high_price,
                        low=low_price,
                        close=close_price,
                        volume=volume,
                        trade_num=0,
                        is_closed_candle=True,
                    )
                )
            except Exception:
                self._logger.warning(
                    "Failed to parse Bybit REST candle",
                    extra={"symbol": symbol, "contract_type": self._category},
                    exc_info=True,
                )
                continue
        return candles
