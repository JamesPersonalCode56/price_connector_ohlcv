"""Circuit breaker pattern implementation for resilient connections."""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Awaitable, Callable, Generic, TypeVar

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failures exceeded, blocking requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""

    pass


class CircuitBreaker(Generic[T]):
    """Circuit breaker with exponential backoff for fault tolerance."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        backoff_base: float = 2.0,
        max_backoff: float = 300.0,
    ) -> None:
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of consecutive failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery (base value)
            half_open_max_calls: Number of test calls allowed in half-open state
            backoff_base: Base for exponential backoff calculation
            max_backoff: Maximum backoff duration in seconds
        """
        self._failure_threshold = failure_threshold
        self._base_recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._backoff_base = backoff_base
        self._max_backoff = max_backoff

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._half_open_calls = 0
        self._consecutive_open_count = 0

        self._logger = logging.getLogger(__name__)

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count

    def _calculate_backoff(self) -> float:
        """Calculate exponential backoff duration."""
        if self._consecutive_open_count == 0:
            return self._base_recovery_timeout

        backoff = self._base_recovery_timeout * (
            self._backoff_base ** (self._consecutive_open_count - 1)
        )
        return min(backoff, self._max_backoff)

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self._state != CircuitState.OPEN:
            return False

        if self._last_failure_time is None:
            return True

        elapsed = time.time() - self._last_failure_time
        required_timeout = self._calculate_backoff()

        return elapsed >= required_timeout

    async def call(self, func: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from func

        Raises:
            CircuitBreakerError: If circuit is open
            Exception: Any exception raised by func
        """
        # Check if we should attempt reset
        if self._should_attempt_reset():
            self._state = CircuitState.HALF_OPEN
            self._half_open_calls = 0
            self._logger.info(
                f"Circuit breaker entering HALF_OPEN state after "
                f"{self._calculate_backoff():.1f}s backoff "
                f"(attempt #{self._consecutive_open_count})"
            )

        # Block if circuit is open
        if self._state == CircuitState.OPEN:
            backoff = self._calculate_backoff()
            raise CircuitBreakerError(
                f"Circuit breaker is OPEN (failures: {self._failure_count}, "
                f"wait: {backoff:.1f}s)"
            )

        # Limit calls in half-open state
        if self._state == CircuitState.HALF_OPEN:
            if self._half_open_calls >= self._half_open_max_calls:
                raise CircuitBreakerError(
                    f"Circuit breaker is HALF_OPEN (test limit reached: "
                    f"{self._half_open_calls}/{self._half_open_max_calls})"
                )
            self._half_open_calls += 1

        # Execute the function
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure()
            raise exc

    def _on_success(self) -> None:
        """Handle successful call."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            # After successful test, close the circuit
            self._logger.info(
                f"Circuit breaker test successful, closing circuit "
                f"(consecutive opens: {self._consecutive_open_count})"
            )
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            self._consecutive_open_count = 0  # Reset on successful recovery
        elif self._state == CircuitState.CLOSED:
            # Reset failure count on success
            if self._failure_count > 0:
                self._logger.debug(
                    f"Resetting failure count after success (was {self._failure_count})"
                )
                self._failure_count = 0

    def _on_failure(self) -> None:
        """Handle failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            # Failed during test, reopen circuit
            self._consecutive_open_count += 1
            backoff = self._calculate_backoff()
            self._logger.warning(
                f"Circuit breaker test failed, reopening circuit "
                f"(consecutive opens: {self._consecutive_open_count}, "
                f"next backoff: {backoff:.1f}s)"
            )
            self._state = CircuitState.OPEN
            self._half_open_calls = 0

        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self._failure_threshold:
                self._consecutive_open_count += 1
                backoff = self._calculate_backoff()
                self._logger.warning(
                    f"Circuit breaker opening after {self._failure_count} failures "
                    f"(backoff: {backoff:.1f}s)"
                )
                self._state = CircuitState.OPEN

    def reset(self) -> None:
        """Manually reset circuit breaker to closed state."""
        self._logger.info("Circuit breaker manually reset")
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._consecutive_open_count = 0
        self._last_failure_time = None


__all__ = ["CircuitBreaker", "CircuitBreakerError", "CircuitState"]
