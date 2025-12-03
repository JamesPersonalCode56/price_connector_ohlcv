"""Message deduplication based on symbol + timestamp."""

from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Tuple

from domain.models import PriceQuote


class QuoteDeduplicator:
    """
    Deduplicates quotes based on (symbol, timestamp) key.

    Uses a sliding window to track recently seen quotes and prevent duplicates
    during reconnections or overlapping REST backfill + WebSocket streams.
    """

    def __init__(
        self,
        window_seconds: float = 120.0,
        max_entries: int = 10000,
        exchange: str = "",
        contract_type: str = "",
    ) -> None:
        """
        Initialize deduplicator.

        Args:
            window_seconds: Time window to track seen quotes (in seconds)
            max_entries: Maximum number of entries to keep (prevents unbounded growth)
            exchange: Exchange name for logging
            contract_type: Contract type for logging
        """
        self._window_seconds = window_seconds
        self._max_entries = max_entries
        self._exchange = exchange
        self._contract_type = contract_type

        # OrderedDict maintains insertion order for efficient cleanup
        self._seen: OrderedDict[Tuple[str, int], datetime] = OrderedDict()
        self._logger = logging.getLogger(__name__)

    def _make_key(self, quote: PriceQuote) -> Tuple[str, int]:
        """Create deduplication key from quote."""
        # Use symbol + timestamp (epoch milliseconds)
        timestamp_ms = int(quote.timestamp.timestamp() * 1000)
        return (quote.symbol, timestamp_ms)

    def _cleanup_old_entries(self, now: datetime) -> None:
        """Remove entries older than the sliding window."""
        cutoff = now - timedelta(seconds=self._window_seconds)
        keys_to_remove = []

        for key, timestamp in self._seen.items():
            if timestamp < cutoff:
                keys_to_remove.append(key)
            else:
                # OrderedDict maintains order, so we can stop at first recent entry
                break

        for key in keys_to_remove:
            del self._seen[key]

        if keys_to_remove:
            self._logger.debug(
                f"Cleaned up {len(keys_to_remove)} old deduplication entries",
                extra={
                    "exchange": self._exchange,
                    "contract_type": self._contract_type,
                    "remaining_entries": len(self._seen),
                },
            )

    def _enforce_max_entries(self) -> None:
        """Enforce maximum entry limit by removing oldest."""
        if len(self._seen) <= self._max_entries:
            return

        excess = len(self._seen) - self._max_entries
        keys_to_remove = list(self._seen.keys())[:excess]

        for key in keys_to_remove:
            del self._seen[key]

        self._logger.warning(
            f"Enforced max entry limit, removed {excess} oldest entries",
            extra={
                "exchange": self._exchange,
                "contract_type": self._contract_type,
                "max_entries": self._max_entries,
            },
        )

    def is_duplicate(self, quote: PriceQuote) -> bool:
        """
        Check if quote is a duplicate.

        Args:
            quote: Quote to check

        Returns:
            True if duplicate, False if new
        """
        now = datetime.now(timezone.utc)
        key = self._make_key(quote)

        # Check if we've seen this key recently
        if key in self._seen:
            self._logger.debug(
                "Duplicate quote detected",
                extra={
                    "exchange": self._exchange,
                    "contract_type": self._contract_type,
                    "symbol": quote.symbol,
                    "timestamp": quote.timestamp.isoformat(),
                },
            )
            return True

        # Not a duplicate, record it
        self._seen[key] = now

        # Periodic cleanup
        if len(self._seen) % 100 == 0:
            self._cleanup_old_entries(now)

        # Enforce max entries
        self._enforce_max_entries()

        return False

    def mark_seen(self, quote: PriceQuote) -> None:
        """
        Explicitly mark a quote as seen without checking for duplicates.

        Args:
            quote: Quote to mark as seen
        """
        now = datetime.now(timezone.utc)
        key = self._make_key(quote)
        self._seen[key] = now

    def clear(self) -> None:
        """Clear all tracked entries."""
        self._seen.clear()
        self._logger.info(
            "Deduplication cache cleared",
            extra={
                "exchange": self._exchange,
                "contract_type": self._contract_type,
            },
        )

    def get_stats(self) -> dict[str, int | float]:
        """Get deduplicator statistics."""
        return {
            "tracked_entries": len(self._seen),
            "window_seconds": self._window_seconds,
            "max_entries": self._max_entries,
        }


__all__ = ["QuoteDeduplicator"]
