from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, cast

import websockets
from websockets.exceptions import ConnectionClosed

from application.use_cases.stream_prices import StreamPrices
from config import SETTINGS
from infrastructure.common.client import SubscriptionError
from infrastructure.common.rest_pool import close_all_clients
from infrastructure.common.shutdown import get_shutdown_handler
from interfaces.health_server import create_health_server
from interfaces.repository_factory import build_price_feed_repository

try:
    import orjson as json_lib  # type: ignore[import-not-found]

    _USING_ORJSON = True
except ImportError:
    import json as json_lib  # type: ignore[no-redef]

    _USING_ORJSON = False


def dumps(obj: Any) -> str:
    if _USING_ORJSON:
        return cast(str, json_lib.dumps(obj).decode("utf-8"))
    return cast(str, json_lib.dumps(obj))


def loads(data: str | bytes) -> Any:
    if _USING_ORJSON:
        payload = data if isinstance(data, bytes) else data.encode("utf-8")
        return json_lib.loads(payload)
    if isinstance(data, bytes):
        return json_lib.loads(data.decode("utf-8"))
    return json_lib.loads(data)


LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Expose price streams over a WebSocket server"
    )
    parser.add_argument(
        "--host",
        default=SETTINGS.ws_server.host,
        help="Host/IP to bind the WebSocket server",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=SETTINGS.ws_server.port,
        help="Port to bind the WebSocket server",
    )
    parser.add_argument(
        "--log-level",
        default=SETTINGS.ws_server.log_level.upper(),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity",
    )
    return parser.parse_args()


async def handle_client(websocket: websockets.WebSocketServerProtocol) -> None:
    try:
        raw = await asyncio.wait_for(
            websocket.recv(), timeout=SETTINGS.ws_server.subscribe_timeout
        )
    except asyncio.TimeoutError:
        await _send_error(
            websocket,
            f"No subscription payload received within {SETTINGS.ws_server.subscribe_timeout:.0f} seconds",
        )
        return
    except ConnectionClosed:
        return

    try:
        payload = loads(raw)
    except Exception:
        await _send_error(websocket, "Subscription payload must be valid JSON")
        return

    try:
        exchange, symbols, contract_type, limit = _validate_subscription_payload(
            payload
        )
    except ValueError as exc:
        await _send_error(websocket, str(exc), exchange=exchange)
        return

    LOGGER.info(
        "Client subscribed",
        extra={
            "exchange": exchange,
            "contract_type": contract_type,
            "symbols": symbols,
            "limit": limit,
        },
    )
    try:
        repository = build_price_feed_repository(exchange, contract_type)
    except ValueError as exc:
        await _send_error(
            websocket, str(exc), exchange=exchange, contract_type=contract_type
        )
        return

    await websocket.send(
        dumps(
            {
                "type": "subscribed",
                "exchange": exchange,
                "contract_type": contract_type,
                "symbols": symbols,
                "limit": limit,
            }
        )
    )

    use_case = StreamPrices(repository)
    stream = use_case.execute(symbols)
    counter = 0

    try:
        while True:
            try:
                quote = await asyncio.wait_for(
                    stream.__anext__(),
                    timeout=SETTINGS.connector.stream_idle_timeout,
                )
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError:
                await _send_error(
                    websocket,
                    (
                        f"No quotes received for {SETTINGS.connector.stream_idle_timeout:.0f} seconds "
                        f"from {exchange}::{contract_type or 'default'}. Subscription cancelled."
                    ),
                    exchange=exchange,
                    contract_type=contract_type,
                    symbols=symbols,
                )
                break
            except SubscriptionError as exc:
                await _send_error(
                    websocket,
                    "Subscription rejected by exchange",
                    exchange=exchange,
                    contract_type=contract_type,
                    symbols=symbols,
                    exchange_message=exc.exchange_message or str(exc),
                )
                break

            response = {
                "type": "quote",
                "current_time": str(datetime.now(timezone.utc)),
                "timestamp": quote.timestamp.astimezone(timezone.utc).isoformat(),
                "exchange": quote.exchange,
                "symbol": quote.symbol,
                "contract_type": quote.contract_type,
                "open": quote.open,
                "high": quote.high,
                "low": quote.low,
                "close": quote.close,
                "volume": quote.volume,
                "trade_num": quote.trade_num,
                "is_closed_candle": quote.is_closed_candle,
            }
            await websocket.send(dumps(response))

            if limit > 0:
                counter += 1
                if counter >= limit:
                    break
    except ConnectionClosed:
        LOGGER.info("Client disconnected")
    except Exception as exc:
        LOGGER.exception("Unexpected error while streaming quotes")
        await _send_error(
            websocket,
            f"Internal streaming error: {exc}",
            exchange=exchange,
            contract_type=contract_type,
            symbols=symbols,
            exchange_message=str(exc),
        )
    finally:
        aclose = getattr(stream, "aclose", None)
        if callable(aclose):
            await aclose()


def _validate_subscription_payload(
    payload: Any,
) -> tuple[str, list[str], str | None, int]:
    if not isinstance(payload, dict):
        raise ValueError("Subscription payload must be an object")

    exchange = payload.get("exchange")
    if not isinstance(exchange, str) or not exchange:
        raise ValueError("Field 'exchange' is required and must be a non-empty string")

    symbols_raw = payload.get("symbols")
    if not isinstance(symbols_raw, list) or not symbols_raw:
        raise ValueError("Field 'symbols' is required and must be a non-empty list")
    if not all(isinstance(symbol, str) and symbol for symbol in symbols_raw):
        raise ValueError("Each symbol must be a non-empty string")

    contract_type = payload.get("contract_type")
    if contract_type is not None and (
        not isinstance(contract_type, str) or not contract_type
    ):
        raise ValueError(
            "Field 'contract_type' must be a non-empty string when provided"
        )

    limit = payload.get("limit", 0)
    if not isinstance(limit, int) or limit < 0:
        raise ValueError("Field 'limit' must be a non-negative integer")

    return exchange, symbols_raw, contract_type, limit


async def _send_error(
    websocket: websockets.WebSocketServerProtocol,
    system_message: str,
    *,
    exchange: str | None = None,
    contract_type: str | None = None,
    symbols: list[str] | None = None,
    exchange_message: str | None = None,
) -> None:
    try:
        payload: dict[str, Any] = {
            "type": "error",
            "message": system_message,
            "system_message": system_message,
        }
        if exchange is not None:
            payload["exchange"] = exchange
        if contract_type is not None:
            payload["contract_type"] = contract_type
        if symbols is not None:
            payload["symbols"] = symbols
        if exchange_message:
            payload["exchange_message"] = exchange_message
        await websocket.send(dumps(payload))
    except ConnectionClosed:
        pass


async def run_server(host: str, port: int) -> None:
    LOGGER.info("Starting WebSocket server", extra={"host": host, "port": port})

    # Setup graceful shutdown
    shutdown_handler = get_shutdown_handler()
    shutdown_handler.setup_signal_handlers()

    # Register cleanup callbacks
    shutdown_handler.register_cleanup(close_all_clients)

    # Start health check server
    health_server = create_health_server()
    if health_server:
        health_server.start()
        shutdown_handler.register_cleanup(health_server.stop)

    # Start WebSocket server
    async with websockets.serve(
        handle_client,
        host,
        port,
        ping_interval=SETTINGS.connector.ws_ping_interval,
        ping_timeout=SETTINGS.connector.ws_ping_timeout,
    ):
        LOGGER.info("WebSocket server ready to accept connections")

        # Wait for shutdown signal
        await shutdown_handler.wait_for_shutdown()

        LOGGER.info("Shutdown signal received, cleaning up...")
        await shutdown_handler.cleanup()

        LOGGER.info("Server shutdown complete")


def main() -> None:
    args = parse_args()
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, args.log_level.upper(), logging.INFO))
    asyncio.run(run_server(args.host, args.port))


if __name__ == "__main__":
    main()
