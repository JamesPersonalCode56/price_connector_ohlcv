"""Enhanced WebSocket client with circuit breaker, dual queues, deduplication, and metrics."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Generic, Iterable, List, TypeVar

import websockets
from websockets import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosed

from config import SETTINGS
from domain.models import PriceQuote
from infrastructure.common.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitState,
)
from infrastructure.common.deduplicator import QuoteDeduplicator
from infrastructure.common.quote_queue import QuoteQueue
from metrics import get_metrics_collector

TConfig = TypeVar("TConfig")


class SubscriptionError(Exception):
    """Raised when a subscription cannot be established for the provided symbols."""

    def __init__(self, message: str, *, exchange_message: str | None = None) -> None:
        super().__init__(message)
        self.exchange_message = exchange_message


class WebSocketPriceFeedClient(ABC, Generic[TConfig]):
    """
    Enhanced WebSocket-based streaming client with:
    - Circuit breaker for fault tolerance
    - Dual-pipeline queue system (closed/open candles)
    - Message deduplication
    - Prometheus + structured logging metrics
    """

    exchange: str
    _QUEUE_SENTINEL = object()

    def __init__(self, config: TConfig) -> None:
        self._config = config
        self._logger = logging.getLogger(self._logger_name())
        self._metrics = get_metrics_collector()

        # Will be initialized per connection group
        self._circuit_breaker: CircuitBreaker[AsyncIterator[PriceQuote]] | None = None
        self._deduplicator: QuoteDeduplicator | None = None

    def _init_connection_components(self, contract_type: str) -> None:
        """Initialize circuit breaker and deduplicator for this connection."""
        self._circuit_breaker = CircuitBreaker[AsyncIterator[PriceQuote]](
            failure_threshold=SETTINGS.connector.circuit_breaker_failure_threshold,
            recovery_timeout=SETTINGS.connector.circuit_breaker_recovery_timeout,
            half_open_max_calls=SETTINGS.connector.circuit_breaker_half_open_calls,
        )

        self._deduplicator = QuoteDeduplicator(
            window_seconds=SETTINGS.connector.deduplication_window_seconds,
            max_entries=SETTINGS.connector.deduplication_max_entries,
            exchange=self.exchange,
            contract_type=contract_type,
        )

    async def stream_ticker_prices(
        self, symbols: Iterable[str]
    ) -> AsyncIterator[PriceQuote]:
        symbols_list = self._prepare_symbols(symbols)
        if not symbols_list:
            return

        # Get contract type for metrics
        contract_type = getattr(self._config, "contract_type", "default")

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

        # Use dual-pipeline queue
        queue = QuoteQueue(
            closed_maxsize=SETTINGS.connector.closed_queue_maxsize,
            open_maxsize=SETTINGS.connector.open_queue_maxsize,
            exchange=self.exchange,
            contract_type=contract_type,
        )
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
            except SubscriptionError:
                stop_event.set()
                # Convert to PriceQuote-like sentinel for error propagation
                # We'll handle this differently - just raise
                raise
            except Exception:
                self._logger.exception(
                    "Unhandled error in WebSocket worker; will retry",
                    extra={"symbols": group, "exchange": self.exchange},
                )
            finally:
                # Signal completion
                pass

        async def _queue_consumer() -> AsyncIterator[PriceQuote]:
            """Consumer that drains queue following priority rules."""
            while not stop_event.is_set() or not queue.empty():
                try:
                    quote = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield quote

                    # Update queue depth metrics periodically
                    if self._metrics:
                        self._metrics.record_queue_depth(
                            self.exchange,
                            contract_type,
                            queue.closed_size,
                            queue.open_size,
                        )
                except asyncio.TimeoutError:
                    continue

        try:
            # Start all workers
            for group in symbol_groups:
                tasks.append(asyncio.create_task(_worker(group)))

            # Consume from queue
            async for quote in _queue_consumer():
                yield quote

            # Wait for all workers to complete
            await asyncio.gather(*tasks, return_exceptions=True)

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
        """Stream quotes from a single WebSocket connection with circuit breaker protection."""
        contract_type = getattr(self._config, "contract_type", "default")

        # Initialize components for this connection
        self._init_connection_components(contract_type)

        if self._circuit_breaker is None or self._deduplicator is None:
            raise RuntimeError("Connection components not initialized")

        while True:
            try:
                # Check circuit breaker before attempting connection
                if self._circuit_breaker.state == CircuitState.OPEN:
                    self._metrics.record_circuit_state(
                        self.exchange, contract_type, "open"
                    )
                    self._logger.warning(
                        "Circuit breaker is OPEN, waiting before retry",
                        extra={
                            "exchange": self.exchange,
                            "contract_type": contract_type,
                            "failures": self._circuit_breaker.failure_count,
                        },
                    )
                    await asyncio.sleep(SETTINGS.connector.reconnect_delay)
                    continue

                # Attempt connection through circuit breaker
                async def _connect_and_stream() -> AsyncIterator[PriceQuote]:
                    async def _stream() -> AsyncIterator[PriceQuote]:
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
                            self._metrics.record_connection(
                                self.exchange, contract_type, active=True
                            )

                            try:
                                await self._on_connected(ws, symbols)
                            except ValueError as exc:
                                raise SubscriptionError(
                                    str(exc), exchange_message=str(exc)
                                ) from exc

                            async for quote in self._message_loop(ws, symbols):
                                yield quote

                            self._metrics.record_connection(
                                self.exchange, contract_type, active=False
                            )

                    return _stream()

                # Execute through circuit breaker
                try:
                    async for quote in await self._circuit_breaker.call(
                        _connect_and_stream
                    ):
                        # Deduplicate
                        if self._deduplicator.is_duplicate(quote):
                            self._metrics.record_duplicate(self.exchange, contract_type)
                            continue

                        # Record metrics
                        self._metrics.record_quote(
                            self.exchange,
                            contract_type,
                            quote.is_closed_candle,
                            quote.timestamp,
                        )

                        yield quote

                except CircuitBreakerError as exc:
                    self._logger.warning(str(exc))
                    await asyncio.sleep(SETTINGS.connector.reconnect_delay)
                    continue

            except asyncio.CancelledError:
                raise
            except SubscriptionError:
                raise
            except Exception as exc:
                self._logger.exception(self._connection_error_message())
                self._metrics.record_error(
                    self.exchange,
                    contract_type,
                    "connection_error",
                    str(exc),
                )

            self._metrics.record_reconnection(self.exchange, contract_type)
            await asyncio.sleep(SETTINGS.connector.reconnect_delay)

    async def _message_loop(
        self,
        ws: WebSocketClientProtocol,
        symbols: list[str],
    ) -> AsyncIterator[PriceQuote]:
        """Message processing loop with inactivity detection."""
        contract_type = getattr(self._config, "contract_type", "default")

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
                    self._metrics.record_error(
                        self.exchange,
                        contract_type,
                        "backfill_error",
                    )
                break
            except ConnectionClosed:
                self._logger.info(self._connection_closed_message())
                break
            except asyncio.CancelledError:
                raise
            except SubscriptionError:
                raise
            except Exception as exc:
                self._logger.exception(self._receive_error_message())
                self._metrics.record_error(
                    self.exchange,
                    contract_type,
                    "receive_error",
                    str(exc),
                )
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
        """Handle inactivity with REST backfill."""
        contract_type = getattr(self._config, "contract_type", "default")

        try:
            backfill_quotes = await self._backfill_quotes(symbols)
            self._metrics.record_rest_backfill(
                self.exchange,
                contract_type,
                success=True,
                quote_count=(
                    len(list(backfill_quotes))
                    if hasattr(backfill_quotes, "__len__")
                    else 0
                ),
            )
            for quote in backfill_quotes:
                yield quote
        except Exception:
            self._metrics.record_rest_backfill(
                self.exchange,
                contract_type,
                success=False,
            )
            raise

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
