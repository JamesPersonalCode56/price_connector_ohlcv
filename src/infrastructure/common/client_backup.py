from __future__ import annotations

import asyncio
import contextlib
import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Generic, Iterable, List, TypeVar, cast

import websockets
from websockets import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosed

from config import SETTINGS
from domain.models import PriceQuote

TConfig = TypeVar("TConfig")


class SubscriptionError(Exception):
    """Raised when a subscription cannot be established for the provided symbols."""

    def __init__(self, message: str, *, exchange_message: str | None = None) -> None:
        super().__init__(message)
        self.exchange_message = exchange_message


class WebSocketPriceFeedClient(ABC, Generic[TConfig]):
    """Shared implementation for websocket-based streaming clients."""

    exchange: str
    _QUEUE_SENTINEL = object()

    def __init__(self, config: TConfig) -> None:
        self._config = config
        self._logger = logging.getLogger(self._logger_name())

    async def stream_ticker_prices(
        self, symbols: Iterable[str]
    ) -> AsyncIterator[PriceQuote]:
        symbols_list = self._prepare_symbols(symbols)
        if not symbols_list:
            return

        symbol_groups = self._chunk_symbols(symbols_list)
        if len(symbol_groups) == 1:
            async for quote in self._stream_single_connection(symbol_groups[0]):
                yield quote
            return

        self._logger.info(
            "Splitting subscription across %d WebSocket connections",
            len(symbol_groups),
            extra={
                "exchange": self.exchange,
                "symbol_count": len(symbols_list),
                "group_size_limit": SETTINGS.connector.max_symbol_per_ws,
            },
        )

        queue: asyncio.Queue[PriceQuote | SubscriptionError | object] = asyncio.Queue()
        stop_event = asyncio.Event()
        tasks: list[asyncio.Task[None]] = []

        async def _worker(group: list[str]) -> None:
            try:
                async for quote in self._stream_single_connection(group):
                    if stop_event.is_set():
                        return
                    await queue.put(quote)
            except asyncio.CancelledError:
                raise
            except SubscriptionError as exc:
                stop_event.set()
                await queue.put(exc)
            except Exception:
                self._logger.exception(
                    "Unhandled error in WebSocket worker; reconnecting",
                    extra={"symbols": group, "exchange": self.exchange},
                )
            finally:
                queue.put_nowait(self._QUEUE_SENTINEL)

        try:
            for group in symbol_groups:
                tasks.append(asyncio.create_task(_worker(group)))
            finished_workers = 0
            while finished_workers < len(tasks):
                item = await queue.get()
                if item is self._QUEUE_SENTINEL:
                    finished_workers += 1
                    continue
                if isinstance(item, SubscriptionError):
                    raise item
                yield cast(PriceQuote, item)
        finally:
            stop_event.set()
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(Exception):
                    await task

    async def _stream_single_connection(
        self, symbols: list[str]
    ) -> AsyncIterator[PriceQuote]:
        while True:
            try:
                try:
                    connect_kwargs = self._build_connection_args(symbols)
                except ValueError as exc:
                    raise SubscriptionError(
                        str(exc), exchange_message=str(exc)
                    ) from exc
                url = connect_kwargs.pop("url")
                async with websockets.connect(
                    url,
                    ping_interval=SETTINGS.connector.ws_ping_interval,
                    ping_timeout=SETTINGS.connector.ws_ping_timeout,
                    **connect_kwargs,
                ) as ws:
                    try:
                        await self._on_connected(ws, symbols)
                    except ValueError as exc:
                        raise SubscriptionError(
                            str(exc), exchange_message=str(exc)
                        ) from exc
                    async for quote in self._message_loop(ws, symbols):
                        yield quote
            except asyncio.CancelledError:
                raise
            except SubscriptionError:
                raise
            except Exception:
                self._logger.exception(self._connection_error_message())

            await asyncio.sleep(SETTINGS.connector.reconnect_delay)

    async def _message_loop(
        self,
        ws: WebSocketClientProtocol,
        symbols: list[str],
    ) -> AsyncIterator[PriceQuote]:
        while True:
            try:
                raw_message = await asyncio.wait_for(
                    ws.recv(),
                    timeout=SETTINGS.connector.inactivity_timeout,
                )
            except asyncio.TimeoutError:
                self._logger.warning(
                    self._inactivity_warning_message(),
                    SETTINGS.connector.inactivity_timeout,
                )
                try:
                    async for quote in self._on_inactivity(symbols):
                        yield quote
                except SubscriptionError:
                    raise
                except Exception:
                    self._logger.exception(
                        "Error during inactivity backfill", extra={"symbols": symbols}
                    )
                break
            except ConnectionClosed:
                self._logger.info(self._connection_closed_message())
                break
            except asyncio.CancelledError:
                raise
            except SubscriptionError:
                raise
            except Exception:
                self._logger.exception(self._receive_error_message())
                break

            message_text = (
                raw_message.decode("utf-8")
                if isinstance(raw_message, bytes)
                else raw_message
            )
            quotes = await self._process_message(message_text, symbols, ws)
            if not quotes:
                continue
            for quote in quotes:
                yield quote

    async def _on_inactivity(self, symbols: list[str]) -> AsyncIterator[PriceQuote]:
        backfill_quotes = await self._backfill_quotes(symbols)
        for quote in backfill_quotes:
            yield quote

    def _logger_name(self) -> str:
        token = self.exchange.lower().replace(" ", "_").replace(".", "")
        return f"{__name__}.{token}"

    def _inactivity_warning_message(self) -> str:
        return f"No {self.exchange} updates for %.1fs, performing REST backfill and reconnect"

    def _connection_error_message(self) -> str:
        return f"{self.exchange} WebSocket connection error; retrying"

    def _connection_closed_message(self) -> str:
        return f"{self.exchange} WebSocket closed; reconnecting"

    def _receive_error_message(self) -> str:
        return f"Error while receiving {self.exchange} message"

    def _prepare_symbols(self, symbols: Iterable[str]) -> list[str]:
        return list(symbols)

    def _chunk_symbols(self, symbols: list[str]) -> list[list[str]]:
        limit = SETTINGS.connector.max_symbol_per_ws
        if limit <= 0 or len(symbols) <= limit:
            return [symbols]
        return [
            symbols[index : index + limit] for index in range(0, len(symbols), limit)
        ]

    @abstractmethod
    def _build_connection_args(self, symbols: list[str]) -> dict[str, Any]:
        """Return keyword arguments passed to websockets.connect (must include `url`)."""

    async def _on_connected(
        self, ws: WebSocketClientProtocol, symbols: list[str]
    ) -> None:
        """Run after the websocket connection has been established."""

    @abstractmethod
    async def _process_message(
        self,
        message_text: str,
        symbols: list[str],
        ws: WebSocketClientProtocol,
    ) -> List[PriceQuote]:
        """Convert a websocket payload into zero or more PriceQuote objects."""

    async def _backfill_quotes(self, symbols: list[str]) -> Iterable[PriceQuote]:
        """Fetch a snapshot when the stream is idle. Defaults to no action."""
        return []


__all__ = ["WebSocketPriceFeedClient", "WebSocketClientProtocol", "SubscriptionError"]
