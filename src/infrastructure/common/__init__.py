from .circuit_breaker import CircuitBreaker, CircuitBreakerError, CircuitState
from .client import SubscriptionError, WebSocketClientProtocol, WebSocketPriceFeedClient
from .deduplicator import QuoteDeduplicator
from .quote_queue import QuoteQueue
from .repository import (
    ContractTypeResolver,
    PriceFeedClientProtocol,
    RegistryBackedPriceFeedRepository,
    WebSocketPriceFeedRepository,
)
from .rest_pool import close_all_clients, get_http_client
from .shutdown import GracefulShutdown, get_shutdown_handler

__all__ = [
    "ContractTypeResolver",
    "PriceFeedClientProtocol",
    "RegistryBackedPriceFeedRepository",
    "WebSocketPriceFeedRepository",
    "WebSocketPriceFeedClient",
    "WebSocketClientProtocol",
    "SubscriptionError",
    "CircuitBreaker",
    "CircuitBreakerError",
    "CircuitState",
    "QuoteDeduplicator",
    "QuoteQueue",
    "get_http_client",
    "close_all_clients",
    "GracefulShutdown",
    "get_shutdown_handler",
]
