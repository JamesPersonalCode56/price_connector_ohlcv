import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from domain.errors import ErrorCode
from domain.models import PriceQuote
from infrastructure.common.client import SubscriptionError
from interfaces.ws_server import main as ws_main
from interfaces.ws_server.router import (
    ConnectionPoolBusyError,
    QueueBackpressureError,
    SharedSubscription,
    SubscriptionRouter,
)


class FakeWebSocket:
    def __init__(self, incoming):
        self._incoming = asyncio.Queue()
        for item in incoming:
            self._incoming.put_nowait(item)
        self.sent = []

    async def recv(self):
        return await self._incoming.get()

    async def send(self, data):
        self.sent.append(data)


def _parse_last_payload(fake_ws: FakeWebSocket):
    assert fake_ws.sent, "No payloads sent"
    return json.loads(fake_ws.sent[-1])


def _mock_settings(stream_timeout: float = 0.01, subscribe_timeout: float = 0.01):
    return SimpleNamespace(
        connector=SimpleNamespace(
            stream_idle_timeout=stream_timeout,
            default_interval="1m",
        ),
        ws_server=SimpleNamespace(subscribe_timeout=subscribe_timeout),
    )


def test_ws_protocol_error(monkeypatch):
    fake_ws = FakeWebSocket(["{not-json"])
    monkeypatch.setattr(ws_main, "SETTINGS", _mock_settings())
    asyncio.run(ws_main.handle_client(fake_ws))
    payload = _parse_last_payload(fake_ws)
    assert payload["code"] == ErrorCode.WS_PROTOCOL_ERROR.value


def test_ws_subscribe_rejected(monkeypatch):
    fake_ws = FakeWebSocket([json.dumps({"exchange": "binance"})])
    monkeypatch.setattr(ws_main, "SETTINGS", _mock_settings())
    asyncio.run(ws_main.handle_client(fake_ws))
    payload = _parse_last_payload(fake_ws)
    assert payload["code"] == ErrorCode.WS_SUBSCRIBE_REJECTED.value


def test_ws_connect_failed(monkeypatch):
    async def _subscribe(*args, **kwargs):
        raise ConnectionError("ws connect failed")

    payload = json.dumps(
        {"exchange": "binance", "symbols": ["BTCUSDT"], "contract_type": "spot"}
    )
    fake_ws = FakeWebSocket([payload])
    monkeypatch.setattr(ws_main, "SETTINGS", _mock_settings())
    monkeypatch.setattr(ws_main, "ROUTER", SimpleNamespace(subscribe=_subscribe))
    asyncio.run(ws_main.handle_client(fake_ws))
    payload = _parse_last_payload(fake_ws)
    assert payload["code"] == ErrorCode.WS_CONNECT_FAILED.value


def test_unsupported_contract_type(monkeypatch):
    async def _subscribe(*args, **kwargs):
        raise ValueError("unsupported contract type")

    payload = json.dumps(
        {"exchange": "binance", "symbols": ["BTCUSDT"], "contract_type": "swap"}
    )
    fake_ws = FakeWebSocket([payload])
    monkeypatch.setattr(ws_main, "SETTINGS", _mock_settings())
    monkeypatch.setattr(ws_main, "ROUTER", SimpleNamespace(subscribe=_subscribe))
    asyncio.run(ws_main.handle_client(fake_ws))
    payload = _parse_last_payload(fake_ws)
    assert payload["code"] == ErrorCode.UNSUPPORTED_CONTRACT_TYPE.value


def test_rate_limited_subscription_error(monkeypatch):
    async def _stream():
        raise SubscriptionError("rate limit", exchange_message="rate limit")
        yield  # pragma: no cover

    async def _subscribe(*args, **kwargs):
        return _stream()

    payload = json.dumps(
        {"exchange": "bybit", "symbols": ["BTCUSDT"], "contract_type": "linear"}
    )
    fake_ws = FakeWebSocket([payload])
    monkeypatch.setattr(ws_main, "SETTINGS", _mock_settings(stream_timeout=0.5))
    monkeypatch.setattr(ws_main, "ROUTER", SimpleNamespace(subscribe=_subscribe))
    asyncio.run(ws_main.handle_client(fake_ws))
    payload = _parse_last_payload(fake_ws)
    assert payload["code"] == ErrorCode.RATE_LIMITED.value


def test_rest_backfill_failed_subscription_error(monkeypatch):
    async def _stream():
        raise SubscriptionError("REST backfill failed", exchange_message="backfill")
        yield  # pragma: no cover

    async def _subscribe(*args, **kwargs):
        return _stream()

    payload = json.dumps(
        {"exchange": "gateio", "symbols": ["BTC_USDT"], "contract_type": "spot"}
    )
    fake_ws = FakeWebSocket([payload])
    monkeypatch.setattr(ws_main, "SETTINGS", _mock_settings(stream_timeout=0.5))
    monkeypatch.setattr(ws_main, "ROUTER", SimpleNamespace(subscribe=_subscribe))
    asyncio.run(ws_main.handle_client(fake_ws))
    payload = _parse_last_payload(fake_ws)
    assert payload["code"] == ErrorCode.REST_BACKFILL_FAILED.value


def test_invalid_symbol_subscription_error(monkeypatch):
    async def _stream():
        raise SubscriptionError("invalid symbol", exchange_message="symbol not found")
        yield  # pragma: no cover

    async def _subscribe(*args, **kwargs):
        return _stream()

    payload = json.dumps(
        {"exchange": "binance", "symbols": ["FOO"], "contract_type": "spot"}
    )
    fake_ws = FakeWebSocket([payload])
    monkeypatch.setattr(ws_main, "SETTINGS", _mock_settings(stream_timeout=0.5))
    monkeypatch.setattr(ws_main, "ROUTER", SimpleNamespace(subscribe=_subscribe))
    asyncio.run(ws_main.handle_client(fake_ws))
    payload = _parse_last_payload(fake_ws)
    assert payload["code"] == ErrorCode.INVALID_SYMBOL.value


def test_ws_stream_timeout(monkeypatch):
    ready = asyncio.Event()

    async def _stream():
        await ready.wait()
        yield  # pragma: no cover

    async def _subscribe(*args, **kwargs):
        return _stream()

    payload = json.dumps(
        {"exchange": "okx", "symbols": ["BTC-USDT"], "contract_type": "swap"}
    )
    fake_ws = FakeWebSocket([payload])
    monkeypatch.setattr(ws_main, "SETTINGS", _mock_settings(stream_timeout=0.01))
    monkeypatch.setattr(ws_main, "ROUTER", SimpleNamespace(subscribe=_subscribe))
    asyncio.run(ws_main.handle_client(fake_ws))
    payload = _parse_last_payload(fake_ws)
    assert payload["code"] == ErrorCode.WS_STREAM_TIMEOUT.value


def test_unknown_error(monkeypatch):
    async def _stream():
        raise RuntimeError("unexpected failure")
        yield  # pragma: no cover

    async def _subscribe(*args, **kwargs):
        return _stream()

    payload = json.dumps(
        {"exchange": "okx", "symbols": ["BTC-USDT"], "contract_type": "swap"}
    )
    fake_ws = FakeWebSocket([payload])
    monkeypatch.setattr(ws_main, "SETTINGS", _mock_settings(stream_timeout=0.5))
    monkeypatch.setattr(ws_main, "ROUTER", SimpleNamespace(subscribe=_subscribe))
    asyncio.run(ws_main.handle_client(fake_ws))
    payload = _parse_last_payload(fake_ws)
    assert payload["code"] == ErrorCode.UNKNOWN.value


def test_queue_backpressure():
    quote = PriceQuote(
        exchange="binance",
        symbol="BTCUSDT",
        contract_type="spot",
        timestamp=datetime.now(timezone.utc),
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        volume=1.0,
        trade_num=0,
        is_closed_candle=False,
    )

    async def _stream():
        yield quote
        yield quote

    async def _run():
        subscription = SharedSubscription(_stream(), max_queue_size=1)
        stream = await subscription.add_subscriber()
        await asyncio.sleep(0.01)
        try:
            for _ in range(3):
                await stream.__anext__()
        except QueueBackpressureError:
            return True
        except StopAsyncIteration:
            return False
        return False

    assert asyncio.run(_run()) is True


def test_connection_pool_busy():
    async def _run():
        router = SubscriptionRouter(max_connections_per_exchange=1)
        router._exchange_counts["binance"] = 1
        try:
            await router.subscribe("binance", "spot", ["BTCUSDT"])
        except ConnectionPoolBusyError:
            return True
        return False

    assert asyncio.run(_run()) is True
