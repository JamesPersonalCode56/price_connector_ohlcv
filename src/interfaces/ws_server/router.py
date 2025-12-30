from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any, Dict, Tuple

from application.use_cases.stream_prices import StreamPrices
from config import SETTINGS
from domain.errors import ErrorCode
from domain.models import PriceQuote
from infrastructure.exchange_config import EXCHANGE_WS_ENDPOINTS
from interfaces.repository_factory import build_price_feed_repository


class QueueBackpressureError(RuntimeError):
    """Raised when subscriber queue overflows."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = ErrorCode.INTERNAL_QUEUE_BACKPRESSURE


class ConnectionPoolBusyError(RuntimeError):
    """Raised when the subscription pool is at capacity."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = ErrorCode.CONNECTION_POOL_BUSY


class SharedSubscription:
    """Fan-out a single price stream to multiple subscribers."""

    def __init__(
        self,
        stream: AsyncIterator[PriceQuote],
        *,
        max_queue_size: int = 1000,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        self._stream = stream
        self._max_queue_size = max_queue_size
        self._on_close = on_close
        self._subscribers: Dict[int, asyncio.Queue[Any]] = {}
        self._pump_task: asyncio.Task[None] | None = None
        self._closed = False
        self._lock = asyncio.Lock()
        self._sentinel = object()
        self._error_sentinel = object()

    async def add_subscriber(self) -> AsyncIterator[PriceQuote]:
        queue: asyncio.Queue[Any] = asyncio.Queue(self._max_queue_size)
        key = id(queue)
        async with self._lock:
            self._subscribers[key] = queue
            if self._pump_task is None:
                self._pump_task = asyncio.create_task(self._pump())

        async def _generator() -> AsyncIterator[PriceQuote]:
            try:
                while True:
                    item = await queue.get()
                    if item is self._sentinel:
                        break
                    if item is self._error_sentinel:
                        raise QueueBackpressureError(
                            "Subscriber queue overflowed; dropping subscriber"
                        )
                    yield item
            finally:
                await self._remove_subscriber(key)

        return _generator()

    async def _remove_subscriber(self, key: int) -> None:
        async with self._lock:
            self._subscribers.pop(key, None)
            if not self._subscribers and self._pump_task is not None:
                self._pump_task.cancel()
                self._pump_task = None
                # Attempt to close underlying stream if it supports aclose
                aclose = getattr(self._stream, "aclose", None)
                if callable(aclose):
                    try:
                        await aclose()
                    except Exception:
                        pass
                self._finalize()

    async def _pump(self) -> None:
        try:
            async for quote in self._stream:
                async with self._lock:
                    if not self._subscribers:
                        break
                    dead: list[int] = []
                    for key, queue in self._subscribers.items():
                        try:
                            queue.put_nowait(quote)
                        except asyncio.QueueFull:
                            dead.append(key)
                    for key in dead:
                        queue = self._subscribers.pop(key, None)
                        if queue is not None:
                            try:
                                queue.get_nowait()
                            except asyncio.QueueEmpty:
                                pass
                            queue.put_nowait(self._error_sentinel)
                    if dead:
                        raise QueueBackpressureError(
                            "Subscriber queue overflowed; dropping subscriber"
                        )
        except asyncio.CancelledError:
            pass
        finally:
            async with self._lock:
                for queue in self._subscribers.values():
                    queue.put_nowait(self._sentinel)
                self._subscribers.clear()
                self._pump_task = None
                self._finalize()

    def _finalize(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._on_close:
            self._on_close()


class SubscriptionRouter:
    """Manage shared subscriptions per (exchange, contract_type) with batching."""

    def __init__(
        self, max_queue_size: int = 1000, max_connections_per_exchange: int = 5
    ) -> None:
        self._subscriptions: Dict[Tuple[str, str, Tuple[str, ...]], SharedSubscription] = {}
        self._exchange_counts: Dict[str, int] = {}
        self._max_queue_size = max_queue_size
        self._max_connections_per_exchange = max_connections_per_exchange
        self._lock = asyncio.Lock()

    async def subscribe(
        self, exchange: str, contract_type: str | None, symbols: list[str]
    ) -> AsyncIterator[PriceQuote]:
        normalized_contract_type = self._normalize_contract_type(exchange, contract_type)
        config = self._get_exchange_config(exchange, normalized_contract_type)
        batches = _chunked(sorted(set(symbols)), config.max_symbols_per_connection)

        async with self._lock:
            streams: list[AsyncIterator[PriceQuote]] = []
            for batch in batches:
                key = (exchange, normalized_contract_type, tuple(batch))
                subscription = self._subscriptions.get(key)
                if subscription is None:
                    if (
                        self._max_connections_per_exchange > 0
                        and self._exchange_counts.get(exchange, 0)
                        >= self._max_connections_per_exchange
                    ):
                        raise ConnectionPoolBusyError(
                            f"Subscription pool is at capacity for exchange {exchange}"
                        )
                    repository = build_price_feed_repository(exchange, normalized_contract_type)
                    stream = StreamPrices(repository).execute(batch)
                    key_for_close = key
                    subscription = SharedSubscription(
                        stream,
                        max_queue_size=self._max_queue_size,
                        on_close=lambda: asyncio.create_task(
                            self._release_subscription(exchange, key_for_close)
                        ),
                    )
                    self._subscriptions[key] = subscription
                    self._exchange_counts[exchange] = self._exchange_counts.get(exchange, 0) + 1
                streams.append(await subscription.add_subscriber())
        return _merge_streams(streams)

    @staticmethod
    def _normalize_contract_type(exchange: str, contract_type: str | None) -> str:
        if contract_type:
            return contract_type
        if exchange == "binance":
            raise ValueError("Binance connector requires a contract type")
        config_map = EXCHANGE_WS_ENDPOINTS.get(exchange, {})
        default = None
        for entry in config_map.values():
            default = entry.default_contract_type
            break
        if default is None:
            raise ValueError(f"Unsupported exchange: {exchange}")
        return default

    @staticmethod
    def _get_exchange_config(exchange: str, contract_type: str) -> Any:
        config_map = EXCHANGE_WS_ENDPOINTS.get(exchange)
        if not config_map or contract_type not in config_map:
            raise ValueError("Unsupported contract type")
        return config_map[contract_type]

    async def _release_subscription(self, exchange: str, key: Tuple[str, str, Tuple[str, ...]]) -> None:
        async with self._lock:
            if key in self._subscriptions:
                self._subscriptions.pop(key, None)
                current = self._exchange_counts.get(exchange, 0)
                self._exchange_counts[exchange] = max(0, current - 1)


def _chunked(sequence: list[str], size: int) -> list[list[str]]:
    if size <= 0:
        return [sequence]
    return [sequence[start : start + size] for start in range(0, len(sequence), size)]


def _merge_streams(streams: list[AsyncIterator[PriceQuote]]) -> AsyncIterator[PriceQuote]:
    queue: asyncio.Queue[PriceQuote | object] = asyncio.Queue()
    sentinel = object()

    async def _pump(stream: AsyncIterator[PriceQuote]) -> None:
        try:
            async for item in stream:
                await queue.put(item)
        finally:
            await queue.put(sentinel)

    async def _merged() -> AsyncIterator[PriceQuote]:
        tasks = [asyncio.create_task(_pump(stream)) for stream in streams]
        finished = 0
        try:
            while finished < len(tasks):
                item = await queue.get()
                if item is sentinel:
                    finished += 1
                    continue
                yield item
        finally:
            for task in tasks:
                task.cancel()

    return _merged()


# Global router instance for WS server
ROUTER = SubscriptionRouter(
    max_queue_size=SETTINGS.connector.router_queue_maxsize,
    max_connections_per_exchange=SETTINGS.connector.max_connections_per_exchange,
)
