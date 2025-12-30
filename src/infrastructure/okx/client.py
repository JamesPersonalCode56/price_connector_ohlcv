from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx

from config import SETTINGS
from domain.models import PriceQuote
from infrastructure.common import WebSocketClientProtocol, WebSocketPriceFeedClient

LOGGER = logging.getLogger(__name__)


@dataclass
class OkxClientConfig:
    base_stream_url: str = "wss://ws.okx.com:8443/ws/v5/business"
    default_inst_type: str | None = None
    interval: str = "1m"


class OkxWebSocketClient(WebSocketPriceFeedClient[OkxClientConfig]):
    exchange = "OKX"

    def __init__(self, config: OkxClientConfig) -> None:
        super().__init__(config)
        self._rest_client = OkxRestClient()

    def _build_connection_args(self, symbols: list[str]) -> dict[str, Any]:
        return {"url": self._config.base_stream_url}

    async def _on_connected(
        self, ws: WebSocketClientProtocol, symbols: list[str]
    ) -> None:
        channel = f"candle{self._config.interval}"
        args = [{"channel": channel, "instId": symbol} for symbol in symbols]
        subscribe_message = json.dumps({"op": "subscribe", "args": args})
        await ws.send(subscribe_message)
        self._logger.info(
            "Subscribed to OKX candles",
            extra={
                "subscription_args": args,
                "endpoint": self._config.base_stream_url,
                "interval": self._config.interval,
            },
        )

    async def _process_message(
        self,
        message_text: str,
        symbols: list[str],
        ws: WebSocketClientProtocol,
    ) -> list[PriceQuote]:
        message = json.loads(message_text)

        event = message.get("event")
        if event in {"subscribe", "unsubscribe", "error"}:
            return []

        arg = message.get("arg") or {}
        symbol = arg.get("instId", "")
        inst_type = arg.get("instType") or self._config.default_inst_type or ""

        data = message.get("data") or []
        quotes: list[PriceQuote] = []
        for entry in data:
            quote = self._entry_to_quote(entry, symbol, inst_type)
            if quote is not None:
                quotes.append(quote)
        return quotes

    async def _backfill_quotes(self, symbols: list[str]) -> Iterable[PriceQuote]:
        try:
            return await self._rest_client.fetch_latest_candles(
                symbols,
                interval=self._config.interval,
                inst_type=self._config.default_inst_type,
            )
        except Exception:
            self._logger.exception("Failed to fetch OKX REST backfill")
            return []

    def _entry_to_quote(
        self,
        entry: Any,
        symbol: str,
        inst_type: str,
    ) -> PriceQuote | None:
        if not isinstance(entry, (list, tuple)) or len(entry) < 6:
            return None

        try:
            timestamp = datetime.fromtimestamp(
                int(float(entry[0])) / 1000, tz=timezone.utc
            )
            open_price = float(entry[1])
            high_price = float(entry[2])
            low_price = float(entry[3])
            close_price = float(entry[4])
            volume = float(entry[5])
        except (TypeError, ValueError):
            return None

        confirm_raw: Any = None
        if len(entry) > 8:
            confirm_raw = entry[8]
        elif len(entry) > 7:
            confirm_raw = entry[7]
        is_closed = str(confirm_raw).lower() in {"1", "true", "t"}

        contract_type = inst_type.lower() if inst_type else ""

        return PriceQuote(
            exchange="okx",
            symbol=symbol,
            contract_type=contract_type,
            timestamp=timestamp,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
            trade_num=0,
            is_closed_candle=is_closed,
        )


class OkxRestClient:
    _BASE_URL = "https://www.okx.com/api/v5/market/candles"

    def __init__(self) -> None:
        self._logger = LOGGER

    async def fetch_latest_candles(
        self,
        symbols: Iterable[str],
        interval: str,
        inst_type: str | None,
    ) -> list[PriceQuote]:
        symbols_list = list(symbols)
        if not symbols_list:
            return []

        async with httpx.AsyncClient(timeout=SETTINGS.connector.rest_timeout) as client:
            tasks = []
            for symbol in symbols_list:
                params: dict[str, str] = {
                    "instId": symbol,
                    "bar": interval,
                    "limit": "1",
                }
                if inst_type:
                    params["instType"] = inst_type
                tasks.append(client.get(self._BASE_URL, params=params))
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        candles: list[PriceQuote] = []
        for symbol, response in zip(symbols_list, responses, strict=False):
            if isinstance(response, BaseException):
                extra = {
                    "symbol": symbol,
                    "contract_type": (inst_type or "").lower(),
                    "error": str(response),
                    "error_type": type(response).__name__,
                }
                if isinstance(response, httpx.TimeoutException):
                    self._logger.warning("OKX REST request timed out", extra=extra)
                else:
                    self._logger.warning(
                        "OKX REST request failed",
                        extra=extra,
                        exc_info=response if isinstance(response, Exception) else False,
                    )
                continue
            try:
                response.raise_for_status()
                payload = response.json()
                data = payload.get("data") or []
                if not data:
                    continue
                entry = data[0]
                if not isinstance(entry, (list, tuple)) or len(entry) < 6:
                    continue
                timestamp = datetime.fromtimestamp(
                    int(float(entry[0])) / 1000, tz=timezone.utc
                )
                open_price = float(entry[1])
                high_price = float(entry[2])
                low_price = float(entry[3])
                close_price = float(entry[4])
                volume = float(entry[5])
                confirm_raw: Any = None
                if len(entry) > 8:
                    confirm_raw = entry[8]
                elif len(entry) > 7:
                    confirm_raw = entry[7]
                is_closed = str(confirm_raw).lower() in {"1", "true", "t"}
                contract_type = (inst_type or "").lower()
                candles.append(
                    PriceQuote(
                        exchange="okx",
                        symbol=symbol,
                        contract_type=contract_type,
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
                    "Failed to parse OKX REST candle",
                    extra={
                        "symbol": symbol,
                        "contract_type": (inst_type or "").lower(),
                    },
                    exc_info=True,
                )
                continue
        return candles
