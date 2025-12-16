"""Graceful shutdown handler for clean service termination."""

from __future__ import annotations

import asyncio
import functools
import logging
import signal
from collections.abc import Awaitable, Callable
from typing import List

LOGGER = logging.getLogger(__name__)


class GracefulShutdown:
    """Handles graceful shutdown on SIGTERM/SIGINT signals."""

    def __init__(self) -> None:
        self._shutdown_event = asyncio.Event()
        self._cleanup_callbacks: List[
            Callable[[], None] | Callable[[], Awaitable[None]]
        ] = []
        self._signals_registered = False

    def register_cleanup(
        self, callback: Callable[[], None] | Callable[[], Awaitable[None]]
    ) -> None:
        """
        Register a cleanup callback to run during shutdown.

        Args:
            callback: Sync or async function to call during shutdown
        """
        self._cleanup_callbacks.append(callback)

    def setup_signal_handlers(self) -> None:
        """Setup SIGTERM and SIGINT handlers."""
        if self._signals_registered:
            return

        loop = asyncio.get_running_loop()

        def _signal_handler(sig: signal.Signals) -> None:
            LOGGER.info(f"Received signal {sig.name}, initiating graceful shutdown")
            self._shutdown_event.set()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, functools.partial(_signal_handler, sig))

        self._signals_registered = True
        LOGGER.info("Signal handlers registered for graceful shutdown")

    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown signal."""
        await self._shutdown_event.wait()

    def is_shutting_down(self) -> bool:
        """Check if shutdown has been initiated."""
        return self._shutdown_event.is_set()

    async def cleanup(self) -> None:
        """Run all registered cleanup callbacks."""
        LOGGER.info(f"Running {len(self._cleanup_callbacks)} cleanup callbacks")

        for callback in self._cleanup_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as exc:
                LOGGER.exception(f"Error during cleanup callback: {exc}")

        LOGGER.info("Cleanup completed")


# Global shutdown handler
_shutdown_handler: GracefulShutdown | None = None


def get_shutdown_handler() -> GracefulShutdown:
    """Get or create global shutdown handler."""
    global _shutdown_handler
    if _shutdown_handler is None:
        _shutdown_handler = GracefulShutdown()
    return _shutdown_handler


__all__ = ["GracefulShutdown", "get_shutdown_handler"]
