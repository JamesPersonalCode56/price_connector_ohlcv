from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

from dotenv import load_dotenv

from logging_config import configure_logging

load_dotenv()
configure_logging()


def _get_env(name: str) -> str | None:
    value = os.getenv(name)
    return value.strip() if value is not None else None


def _get_float(name: str, default: float) -> float:
    raw = _get_env(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:  # noqa: TRY003 - propagate config errors clearly
        raise ValueError(f"Environment variable {name} must be a float") from exc


def _get_int(name: str, default: int) -> int:
    raw = _get_env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:  # noqa: TRY003 - propagate config errors clearly
        raise ValueError(f"Environment variable {name} must be an integer") from exc


def _get_str(name: str, default: str) -> str:
    raw = _get_env(name)
    return raw if raw is not None else default


@dataclass(frozen=True)
class ConnectorSettings:
    inactivity_timeout: float
    reconnect_delay: float
    rest_timeout: float
    ws_ping_interval: float
    ws_ping_timeout: float
    stream_idle_timeout: float
    max_symbol_per_ws: int
    # Circuit breaker settings
    circuit_breaker_failure_threshold: int
    circuit_breaker_recovery_timeout: float
    circuit_breaker_half_open_calls: int
    # Queue settings
    closed_queue_maxsize: int
    open_queue_maxsize: int | None
    # Deduplication settings
    deduplication_window_seconds: float
    deduplication_max_entries: int
    # Connection pooling
    rest_pool_connections: int
    rest_pool_maxsize: int


@dataclass(frozen=True)
class WsServerSettings:
    host: str
    port: int
    log_level: str
    subscribe_timeout: float
    # Health check settings
    health_check_port: int
    health_check_enabled: bool


@dataclass(frozen=True)
class Settings:
    connector: ConnectorSettings
    ws_server: WsServerSettings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    connector = ConnectorSettings(
        inactivity_timeout=_get_float("CONNECTOR_INACTIVITY_TIMEOUT", 3.0),
        reconnect_delay=_get_float("CONNECTOR_RECONNECT_DELAY", 1.0),
        rest_timeout=_get_float("CONNECTOR_REST_TIMEOUT", 5.0),
        ws_ping_interval=_get_float("CONNECTOR_WS_PING_INTERVAL", 20.0),
        ws_ping_timeout=_get_float("CONNECTOR_WS_PING_TIMEOUT", 20.0),
        stream_idle_timeout=_get_float("CONNECTOR_STREAM_IDLE_TIMEOUT", 10.0),
        max_symbol_per_ws=_get_int("CONNECTOR_MAX_SYMBOL_PER_WS", 50),
        # Circuit breaker
        circuit_breaker_failure_threshold=_get_int("CONNECTOR_CIRCUIT_BREAKER_FAILURE_THRESHOLD", 5),
        circuit_breaker_recovery_timeout=_get_float("CONNECTOR_CIRCUIT_BREAKER_RECOVERY_TIMEOUT", 30.0),
        circuit_breaker_half_open_calls=_get_int("CONNECTOR_CIRCUIT_BREAKER_HALF_OPEN_CALLS", 1),
        # Queues
        closed_queue_maxsize=_get_int("CONNECTOR_CLOSED_QUEUE_MAXSIZE", 1000),
        open_queue_maxsize=_get_int("CONNECTOR_OPEN_QUEUE_MAXSIZE", 0) or None,  # 0 = unbounded
        # Deduplication
        deduplication_window_seconds=_get_float("CONNECTOR_DEDUPLICATION_WINDOW_SECONDS", 120.0),
        deduplication_max_entries=_get_int("CONNECTOR_DEDUPLICATION_MAX_ENTRIES", 10000),
        # Connection pooling
        rest_pool_connections=_get_int("CONNECTOR_REST_POOL_CONNECTIONS", 10),
        rest_pool_maxsize=_get_int("CONNECTOR_REST_POOL_MAXSIZE", 20),
    )

    ws_server = WsServerSettings(
        host=_get_str("CONNECTOR_WSS_HOST", "0.0.0.0"),
        port=_get_int("CONNECTOR_WSS_PORT", 8765),
        log_level=_get_str("CONNECTOR_WSS_LOG_LEVEL", "INFO"),
        subscribe_timeout=_get_float("CONNECTOR_WSS_SUBSCRIBE_TIMEOUT", 10.0),
        health_check_port=_get_int("CONNECTOR_WSS_HEALTH_CHECK_PORT", 8766),
        health_check_enabled=_get_str("CONNECTOR_WSS_HEALTH_CHECK_ENABLED", "true").lower() == "true",
    )

    return Settings(connector=connector, ws_server=ws_server)


SETTINGS: Final[Settings] = get_settings()
