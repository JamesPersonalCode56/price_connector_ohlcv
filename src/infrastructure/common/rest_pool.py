"""HTTP connection pooling for REST API clients."""

from __future__ import annotations

import httpx
from typing import Dict

from config import SETTINGS

# Global connection pool per exchange
_http_clients: Dict[str, httpx.AsyncClient] = {}


def get_http_client(exchange: str) -> httpx.AsyncClient:
    """
    Get or create a pooled HTTP client for an exchange.

    Args:
        exchange: Exchange name

    Returns:
        Configured httpx.AsyncClient with connection pooling
    """
    if exchange not in _http_clients:
        _http_clients[exchange] = httpx.AsyncClient(
            timeout=httpx.Timeout(SETTINGS.connector.rest_timeout),
            limits=httpx.Limits(
                max_connections=SETTINGS.connector.rest_pool_maxsize,
                max_keepalive_connections=SETTINGS.connector.rest_pool_connections,
            ),
            http2=True,  # Enable HTTP/2 for better performance
        )

    return _http_clients[exchange]


async def close_all_clients() -> None:
    """Close all HTTP clients (call during shutdown)."""
    for client in _http_clients.values():
        await client.aclose()
    _http_clients.clear()


__all__ = ["get_http_client", "close_all_clients"]
