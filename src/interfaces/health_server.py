"""HTTP health check server for monitoring and observability."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any

try:
    import orjson as json_lib

    def dumps(obj: Any) -> bytes:
        return json_lib.dumps(obj)

except ImportError:
    import json as json_lib_fallback

    def dumps(obj: Any) -> bytes:
        return json_lib_fallback.dumps(obj).encode("utf-8")


from prometheus_client import REGISTRY, generate_latest

from config import SETTINGS
from metrics import get_metrics_collector

LOGGER = logging.getLogger(__name__)


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler for health check and metrics endpoints."""

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default HTTP logging (we use our own logger)."""
        pass

    def _send_response(
        self, status: int, content: bytes, content_type: str = "text/plain"
    ) -> None:
        """Send HTTP response."""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        """Handle GET requests."""
        if self.path == "/health":
            self._handle_health()
        elif self.path == "/ready":
            self._handle_ready()
        elif self.path == "/metrics":
            self._handle_metrics()
        else:
            self._send_response(404, b"Not Found\n")

    def _handle_health(self) -> None:
        """
        Handle /health endpoint - basic liveness check.

        Returns 200 if server is alive.
        """
        response = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._send_response(200, dumps(response), "application/json")

    def _handle_ready(self) -> None:
        """
        Handle /ready endpoint - readiness check with exchange health.

        Returns 200 if at least one exchange has active connections,
        503 if no connections or all exchanges unhealthy.
        """
        metrics_collector = get_metrics_collector()
        health_metrics = metrics_collector.get_health_metrics()

        exchanges = []
        has_active_connections = False

        for health in health_metrics:
            if not health.exchange:  # Skip uninitialized entries
                continue

            is_healthy = (
                health.active_connections > 0
                and health.last_message_time is not None
                and (
                    datetime.now(timezone.utc) - health.last_message_time
                ).total_seconds()
                < 60
            )

            if is_healthy:
                has_active_connections = True

            exchanges.append(
                {
                    "exchange": health.exchange,
                    "contract_type": health.contract_type,
                    "active_connections": health.active_connections,
                    "last_message_time": (
                        health.last_message_time.isoformat()
                        if health.last_message_time
                        else None
                    ),
                    "total_quotes": health.total_quotes,
                    "total_errors": health.total_errors,
                    "consecutive_failures": health.consecutive_failures,
                    "circuit_state": health.circuit_state,
                    "healthy": is_healthy,
                }
            )

        status_code = 200 if has_active_connections else 503
        response = {
            "status": "ready" if has_active_connections else "not_ready",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "exchanges": exchanges,
        }

        self._send_response(status_code, dumps(response), "application/json")

    def _handle_metrics(self) -> None:
        """
        Handle /metrics endpoint - Prometheus metrics.

        Returns metrics in Prometheus text format.
        """
        metrics_data = generate_latest(REGISTRY)
        self._send_response(200, metrics_data, "text/plain; version=0.0.4")


class HealthCheckServer:
    """HTTP server for health checks running in background thread."""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._server: HTTPServer | None = None
        self._thread: Thread | None = None

    def start(self) -> None:
        """Start health check server in background thread."""
        if self._server is not None:
            LOGGER.warning("Health check server already running")
            return

        self._server = HTTPServer((self._host, self._port), HealthCheckHandler)

        def _run_server() -> None:
            LOGGER.info(
                "Health check server started",
                extra={"host": self._host, "port": self._port},
            )
            if self._server is None:
                raise RuntimeError("Health check server not initialized")
            self._server.serve_forever()

        self._thread = Thread(target=_run_server, daemon=True, name="HealthCheckServer")
        self._thread.start()

        LOGGER.info(
            "Health check endpoints available:",
            extra={
                "health": f"http://{self._host}:{self._port}/health",
                "ready": f"http://{self._host}:{self._port}/ready",
                "metrics": f"http://{self._host}:{self._port}/metrics",
            },
        )

    def stop(self) -> None:
        """Stop health check server."""
        if self._server is None:
            return

        LOGGER.info("Stopping health check server")
        self._server.shutdown()
        self._server.server_close()
        self._server = None

        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None


def create_health_server() -> HealthCheckServer | None:
    """Create health check server if enabled in configuration."""
    if not SETTINGS.ws_server.health_check_enabled:
        LOGGER.info("Health check server disabled in configuration")
        return None

    return HealthCheckServer(
        host=SETTINGS.ws_server.host,
        port=SETTINGS.ws_server.health_check_port,
    )


__all__ = ["HealthCheckServer", "create_health_server"]
