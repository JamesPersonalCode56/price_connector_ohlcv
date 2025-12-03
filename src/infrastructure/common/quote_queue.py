"""Dual-pipeline queue system for quote routing with backpressure control."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Deque, Generic, TypeVar

from domain.models import PriceQuote

T = TypeVar("T")


class QuoteQueue:
    """
    Dual-pipeline queue for PriceQuote routing.

    Closed candles (is_closed=True) go into a bounded queue with backpressure.
    Open candles (is_closed=False) go into an unbounded LIFO stack.

    Consumer always drains closed queue first, then pops from open stack in LIFO order.
    """

    def __init__(
        self,
        closed_maxsize: int = 1000,
        open_maxsize: int | None = None,
        exchange: str = "",
        contract_type: str = "",
    ) -> None:
        """
        Initialize dual-pipeline queue.

        Args:
            closed_maxsize: Maximum size for closed candle queue (enforces backpressure)
            open_maxsize: Optional maximum size for open candle stack (None = unbounded)
            exchange: Exchange name for logging/metrics
            contract_type: Contract type for logging/metrics
        """
        self._closed_queue: asyncio.Queue[PriceQuote] = asyncio.Queue(maxsize=closed_maxsize)
        self._open_stack: Deque[PriceQuote] = deque()
        self._open_maxsize = open_maxsize
        self._closed_maxsize = closed_maxsize

        self._exchange = exchange
        self._contract_type = contract_type

        self._blocking_events = 0
        self._open_overflow_events = 0

        self._logger = logging.getLogger(__name__)
        self._lock = asyncio.Lock()  # Protect deque operations

    @property
    def closed_size(self) -> int:
        """Get current size of closed candle queue."""
        return self._closed_queue.qsize()

    @property
    def open_size(self) -> int:
        """Get current size of open candle stack."""
        return len(self._open_stack)

    @property
    def blocking_events(self) -> int:
        """Get count of blocking events (backpressure applied)."""
        return self._blocking_events

    @property
    def open_overflow_events(self) -> int:
        """Get count of open stack overflow events."""
        return self._open_overflow_events

    async def put(self, item: PriceQuote) -> None:
        """
        Put an item into the appropriate queue/stack.

        Args:
            item: PriceQuote to route

        Raises:
            asyncio.QueueFull: If closed queue is full (caller should retry)
        """
        if item.is_closed_candle:
            # Closed candles go to bounded queue (may block)
            if self._closed_queue.full():
                self._blocking_events += 1
                self._logger.warning(
                    "Closed queue full, applying backpressure",
                    extra={
                        "exchange": self._exchange,
                        "contract_type": self._contract_type,
                        "closed_size": self.closed_size,
                        "blocking_events": self._blocking_events,
                    },
                )

            await self._closed_queue.put(item)

        else:
            # Open candles go to LIFO stack
            async with self._lock:
                if self._open_maxsize is not None and len(self._open_stack) >= self._open_maxsize:
                    # Drop oldest (bottom) item if overflow
                    self._open_overflow_events += 1
                    if self._open_stack:
                        dropped = self._open_stack.popleft()
                        self._logger.warning(
                            "Open stack overflow, dropping oldest item",
                            extra={
                                "exchange": self._exchange,
                                "contract_type": self._contract_type,
                                "open_size": self.open_size,
                                "dropped_symbol": dropped.symbol,
                                "overflow_events": self._open_overflow_events,
                            },
                        )

                self._open_stack.append(item)

    async def get(self) -> PriceQuote:
        """
        Get next item following priority rules.

        Priority:
        1. Closed queue (FIFO)
        2. Open stack (LIFO)
        3. Wait if both empty

        Returns:
            Next PriceQuote to process

        Raises:
            asyncio.CancelledError: If cancelled while waiting
        """
        while True:
            # Priority 1: Drain closed queue first
            try:
                return self._closed_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass

            # Priority 2: Pop from open stack (LIFO)
            async with self._lock:
                if self._open_stack:
                    return self._open_stack.pop()

            # Both empty, wait briefly and retry
            await asyncio.sleep(0.01)

    async def get_nowait(self) -> PriceQuote | None:
        """
        Non-blocking get with same priority rules.

        Returns:
            Next PriceQuote or None if both queues empty
        """
        # Priority 1: Closed queue
        try:
            return self._closed_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

        # Priority 2: Open stack
        async with self._lock:
            if self._open_stack:
                return self._open_stack.pop()

        return None

    def empty(self) -> bool:
        """Check if both queues are empty."""
        return self._closed_queue.empty() and len(self._open_stack) == 0

    def get_metrics(self) -> dict[str, int]:
        """Get current queue metrics."""
        return {
            "closed_size": self.closed_size,
            "open_size": self.open_size,
            "blocking_events": self._blocking_events,
            "open_overflow_events": self._open_overflow_events,
            "closed_maxsize": self._closed_maxsize,
            "open_maxsize": self._open_maxsize or -1,
        }


__all__ = ["QuoteQueue"]
