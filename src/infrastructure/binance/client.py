from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx

try:
    import orjson as json
except ImportError:
    import json  # type: ignore

from domain.models import PriceQuote
from infrastructure.common import WebSocketClientProtocol, WebSocketPriceFeedClient
from infrastructure.common.rest_pool import get_http_client

LOGGER = logging.getLogger(__name__)


@dataclass
class BinanceWsConfig:
    contract_type: str
    base_stream_url: str
    interval: str = "1m"

    def build_stream_url(self, symbols: Iterable[str]) -> str:
        streams = "/".join(
            f"{symbol.lower()}@kline_{self.interval}" for symbol in symbols
        )
        base = self.base_stream_url
        if base.endswith("/ws"):
            base = base[: -len("/ws")]
        return f"{base}/stream?streams={streams}"


class BinanceWebSocketClient(WebSocketPriceFeedClient[BinanceWsConfig]):
    """Minimal WebSocket client for Binance combined ticker streams."""

    exchange = "Binance"

    def __init__(self, config: BinanceWsConfig) -> None:
        super().__init__(config)
        self._rest_client = BinanceRestClient(config.contract_type, config.interval)

    def _build_connection_args(self, symbols: list[str]) -> dict[str, Any]:
        return {"url": self._config.build_stream_url(symbols)}

    async def _on_connected(
        self, ws: WebSocketClientProtocol, symbols: list[str]
    ) -> None:
        url = self._config.build_stream_url(symbols)
        self._logger.info(
            "Connected to Binance WS stream", extra={"url": url, "symbols": symbols}
        )

    def _inactivity_warning_message(self) -> str:
        return "No Binance updates for %.1fs, attempting REST backfill and reconnect"

    async def _process_message(
        self,
        message_text: str,
        symbols: list[str],
        ws: WebSocketClientProtocol,
    ) -> list[PriceQuote]:
        try:
            quote = self._message_to_quote(message_text)
        except ValueError:
            return []
        return [quote]

    async def _backfill_quotes(self, symbols: list[str]) -> Iterable[PriceQuote]:
        try:
            return await self._rest_client.fetch_latest_candles(symbols)
        except Exception:
            self._logger.exception("Failed to fetch Binance REST backfill")
            return []

    def _message_to_quote(self, raw_message: str) -> PriceQuote:
        # orjson requires bytes, standard json requires str
        if json.__name__ == "orjson":
            payload = json.loads(
                raw_message.encode("utf-8")
                if isinstance(raw_message, str)
                else raw_message
            )
        else:
            payload = json.loads(raw_message)
        data = payload.get("data", payload)
        kline = data.get("k", {})

        symbol = kline.get("s") or data.get("s", "")

        try:
            open_price = float(kline["o"])
            high_price = float(kline["h"])
            low_price = float(kline["l"])
            close_price = float(kline["c"])
            volume = float(kline.get("v", 0.0))
            trade_num = int(kline.get("n", 0))
        except (KeyError, TypeError, ValueError) as exc:
            self._logger.debug(
                "Discarding Binance kline message due to missing fields",
                extra={"payload": payload},
                exc_info=True,
            )
            raise ValueError("Invalid Binance kline payload") from exc

        close_timestamp = data.get("E") or kline.get("T")
        if close_timestamp is None:
            timestamp = datetime.now(timezone.utc)
        else:
            timestamp = datetime.fromtimestamp(
                int(close_timestamp) / 1000, tz=timezone.utc
            )

        return PriceQuote(
            exchange="binance",
            symbol=symbol,
            contract_type=self._config.contract_type,
            timestamp=timestamp,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
            trade_num=trade_num,
            is_closed_candle=bool(kline.get("x", False)),
        )


class BinanceRestClient:
    _BASE_URLS = {
        "spot": "https://api.binance.com/api/v3/klines",
        "usdm": "https://fapi.binance.com/fapi/v1/klines",
        "coinm": "https://dapi.binance.com/dapi/v1/klines",
    }

    def __init__(self, contract_type: str, interval: str) -> None:
        if contract_type not in self._BASE_URLS:
            raise ValueError(
                f"Unsupported Binance contract_type for REST backfill: {contract_type}"
            )
        self._logger = LOGGER
        self._contract_type = contract_type
        self._base_url = self._BASE_URLS[contract_type]
        self._interval = interval

    async def fetch_latest_candles(self, symbols: Iterable[str]) -> list[PriceQuote]:
        symbols_list = list(symbols)
        if not symbols_list:
            return []

        client = get_http_client("binance")
        tasks = [
            client.get(
                self._base_url,
                params={
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
                extra = {
                    "symbol": symbol,
                    "contract_type": self._contract_type,
                    "error": str(response),
                    "error_type": type(response).__name__,
                }
                if isinstance(response, httpx.TimeoutException):
                    self._logger.warning("Binance REST request timed out", extra=extra)
                else:
                    self._logger.warning(
                        "Binance REST request failed",
                        extra=extra,
                        exc_info=response if isinstance(response, Exception) else False,
                    )
                continue
            try:
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, list) or not data:
                    continue
                candle = data[0]
                close_time = candle[6]
                timestamp = datetime.fromtimestamp(
                    int(close_time) / 1000, tz=timezone.utc
                )
                open_price = float(candle[1])
                high_price = float(candle[2])
                low_price = float(candle[3])
                close_price = float(candle[4])
                volume = float(candle[5])
                trade_num = int(candle[8]) if len(candle) > 8 else 0
                candles.append(
                    PriceQuote(
                        exchange="binance",
                        symbol=symbol,
                        contract_type=self._contract_type,
                        timestamp=timestamp,
                        open=open_price,
                        high=high_price,
                        low=low_price,
                        close=close_price,
                        volume=volume,
                        trade_num=trade_num,
                        is_closed_candle=True,
                    )
                )
            except Exception:
                self._logger.warning(
                    "Failed to parse Binance REST candle",
                    extra={"symbol": symbol, "contract_type": self._contract_type},
                    exc_info=True,
                )
                continue
        return candles
