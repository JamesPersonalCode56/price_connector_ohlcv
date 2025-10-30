"""Metrics collection for monitoring and observability.

Provides both structured logging metrics and Prometheus-compatible metrics.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import DefaultDict

from prometheus_client import Counter, Gauge, Histogram, Info

# Prometheus metrics
QUOTES_PROCESSED = Counter(
    "connector_quotes_processed_total",
    "Total number of quotes processed",
    ["exchange", "contract_type", "is_closed"],
)

QUOTES_LATENCY = Histogram(
    "connector_quote_latency_seconds",
    "Latency between exchange timestamp and processing time",
    ["exchange", "contract_type"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0),
)

ACTIVE_CONNECTIONS = Gauge(
    "connector_active_connections",
    "Number of active WebSocket connections",
    ["exchange", "contract_type"],
)

CONNECTION_ERRORS = Counter(
    "connector_connection_errors_total",
    "Total number of connection errors",
    ["exchange", "contract_type", "error_type"],
)

RECONNECTIONS = Counter(
    "connector_reconnections_total",
    "Total number of reconnection attempts",
    ["exchange", "contract_type"],
)

REST_BACKFILLS = Counter(
    "connector_rest_backfills_total",
    "Total number of REST backfill operations",
    ["exchange", "contract_type", "status"],
)

QUEUE_DEPTH_CLOSED = Gauge(
    "connector_queue_depth_closed",
    "Current depth of closed candle queue",
    ["exchange", "contract_type"],
)

QUEUE_DEPTH_OPEN = Gauge(
    "connector_queue_depth_open",
    "Current depth of open candle stack",
    ["exchange", "contract_type"],
)

QUEUE_BLOCKING_EVENTS = Counter(
    "connector_queue_blocking_events_total",
    "Number of times producer blocked on full queue",
    ["exchange", "contract_type"],
)

CIRCUIT_BREAKER_STATE = Gauge(
    "connector_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half-open)",
    ["exchange", "contract_type"],
)

DUPLICATES_FILTERED = Counter(
    "connector_duplicates_filtered_total",
    "Number of duplicate quotes filtered",
    ["exchange", "contract_type"],
)

CONNECTOR_INFO = Info(
    "connector_build",
    "Connector build information",
)

# Set build info
CONNECTOR_INFO.info({"version": "0.2.0", "architecture": "clean"})


@dataclass
class ExchangeHealthMetrics:
    """Health metrics for a single exchange connection."""

    exchange: str
    contract_type: str
    active_connections: int = 0
    last_message_time: datetime | None = None
    total_quotes: int = 0
    total_errors: int = 0
    consecutive_failures: int = 0
    circuit_state: str = "closed"  # closed, open, half_open
    last_error: str | None = None


class MetricsCollector:
    """Centralized metrics collector with thread-safe operations."""

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)
        self._lock = Lock()
        self._health: DefaultDict[tuple[str, str], ExchangeHealthMetrics] = defaultdict(
            lambda: ExchangeHealthMetrics(exchange="", contract_type="")
        )

    def record_quote(
        self,
        exchange: str,
        contract_type: str,
        is_closed: bool,
        exchange_timestamp: datetime,
    ) -> None:
        """Record a processed quote with latency measurement."""
        now = datetime.now(timezone.utc)
        latency = (now - exchange_timestamp).total_seconds()

        # Prometheus metrics
        QUOTES_PROCESSED.labels(
            exchange=exchange,
            contract_type=contract_type,
            is_closed=str(is_closed),
        ).inc()

        QUOTES_LATENCY.labels(
            exchange=exchange,
            contract_type=contract_type,
        ).observe(latency)

        # Health metrics
        with self._lock:
            key = (exchange, contract_type)
            health = self._health[key]
            health.exchange = exchange
            health.contract_type = contract_type
            health.last_message_time = now
            health.total_quotes += 1
            health.consecutive_failures = 0  # Reset on success

        # Structured logging
        self._logger.info(
            "Quote processed",
            extra={
                "exchange": exchange,
                "contract_type": contract_type,
                "is_closed": is_closed,
                "latency_ms": round(latency * 1000, 2),
            },
        )

    def record_connection(self, exchange: str, contract_type: str, active: bool) -> None:
        """Record connection state change."""
        delta = 1 if active else -1

        ACTIVE_CONNECTIONS.labels(
            exchange=exchange,
            contract_type=contract_type,
        ).inc(delta)

        with self._lock:
            key = (exchange, contract_type)
            health = self._health[key]
            health.exchange = exchange
            health.contract_type = contract_type
            health.active_connections = max(0, health.active_connections + delta)

        self._logger.info(
            f"Connection {'established' if active else 'closed'}",
            extra={
                "exchange": exchange,
                "contract_type": contract_type,
                "active_connections": health.active_connections,
            },
        )

    def record_error(
        self,
        exchange: str,
        contract_type: str,
        error_type: str,
        error_message: str | None = None,
    ) -> None:
        """Record a connection or processing error."""
        CONNECTION_ERRORS.labels(
            exchange=exchange,
            contract_type=contract_type,
            error_type=error_type,
        ).inc()

        with self._lock:
            key = (exchange, contract_type)
            health = self._health[key]
            health.exchange = exchange
            health.contract_type = contract_type
            health.total_errors += 1
            health.consecutive_failures += 1
            if error_message:
                health.last_error = error_message[:200]  # Truncate

        self._logger.warning(
            f"Error recorded: {error_type}",
            extra={
                "exchange": exchange,
                "contract_type": contract_type,
                "error_type": error_type,
                "error_message": error_message,
            },
        )

    def record_reconnection(self, exchange: str, contract_type: str) -> None:
        """Record a reconnection attempt."""
        RECONNECTIONS.labels(
            exchange=exchange,
            contract_type=contract_type,
        ).inc()

        self._logger.info(
            "Reconnection attempt",
            extra={"exchange": exchange, "contract_type": contract_type},
        )

    def record_rest_backfill(
        self,
        exchange: str,
        contract_type: str,
        success: bool,
        quote_count: int = 0,
    ) -> None:
        """Record a REST backfill operation."""
        status = "success" if success else "failure"

        REST_BACKFILLS.labels(
            exchange=exchange,
            contract_type=contract_type,
            status=status,
        ).inc()

        self._logger.info(
            f"REST backfill {status}",
            extra={
                "exchange": exchange,
                "contract_type": contract_type,
                "quote_count": quote_count,
            },
        )

    def record_queue_depth(
        self,
        exchange: str,
        contract_type: str,
        closed_depth: int,
        open_depth: int,
    ) -> None:
        """Record current queue depths."""
        QUEUE_DEPTH_CLOSED.labels(
            exchange=exchange,
            contract_type=contract_type,
        ).set(closed_depth)

        QUEUE_DEPTH_OPEN.labels(
            exchange=exchange,
            contract_type=contract_type,
        ).set(open_depth)

    def record_queue_blocking(self, exchange: str, contract_type: str) -> None:
        """Record a queue blocking event (backpressure)."""
        QUEUE_BLOCKING_EVENTS.labels(
            exchange=exchange,
            contract_type=contract_type,
        ).inc()

        self._logger.warning(
            "Queue blocking - backpressure applied",
            extra={"exchange": exchange, "contract_type": contract_type},
        )

    def record_circuit_state(
        self,
        exchange: str,
        contract_type: str,
        state: str,
    ) -> None:
        """Record circuit breaker state change."""
        state_map = {"closed": 0, "open": 1, "half_open": 2}
        state_value = state_map.get(state, 0)

        CIRCUIT_BREAKER_STATE.labels(
            exchange=exchange,
            contract_type=contract_type,
        ).set(state_value)

        with self._lock:
            key = (exchange, contract_type)
            health = self._health[key]
            health.exchange = exchange
            health.contract_type = contract_type
            health.circuit_state = state

        self._logger.warning(
            f"Circuit breaker state changed to {state}",
            extra={"exchange": exchange, "contract_type": contract_type, "state": state},
        )

    def record_duplicate(self, exchange: str, contract_type: str) -> None:
        """Record a duplicate quote that was filtered."""
        DUPLICATES_FILTERED.labels(
            exchange=exchange,
            contract_type=contract_type,
        ).inc()

        self._logger.debug(
            "Duplicate quote filtered",
            extra={"exchange": exchange, "contract_type": contract_type},
        )

    def get_health_metrics(self) -> list[ExchangeHealthMetrics]:
        """Get health metrics for all exchanges."""
        with self._lock:
            return list(self._health.values())

    def get_exchange_health(
        self,
        exchange: str,
        contract_type: str,
    ) -> ExchangeHealthMetrics | None:
        """Get health metrics for a specific exchange."""
        with self._lock:
            key = (exchange, contract_type)
            return self._health.get(key)


# Global metrics collector instance
_metrics_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create the global metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


__all__ = [
    "MetricsCollector",
    "ExchangeHealthMetrics",
    "get_metrics_collector",
]
