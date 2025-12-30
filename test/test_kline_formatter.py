from datetime import datetime, timezone

from domain.models import PriceQuote


def test_to_kline_payload():
    quote = PriceQuote(
        exchange="binance",
        symbol="BTCUSDT",
        contract_type="spot",
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=100.0,
        trade_num=0,
        is_closed_candle=False,
    )
    event_time = datetime(2024, 1, 1, 0, 0, 1, tzinfo=timezone.utc)
    payload = quote.to_kline_event(event_time=event_time, interval="1m")

    assert payload["e"] == "kline"
    assert payload["s"] == "BTCUSDT"
    assert payload["E"] == int(event_time.timestamp() * 1000)
    k = payload["k"]
    assert k["s"] == "BTCUSDT"
    assert k["i"] == "1m"
    assert k["o"] == 1.0
    assert k["c"] == 1.5
    assert k["h"] == 2.0
    assert k["l"] == 0.5
    assert k["v"] == 100.0
    assert k["x"] is False
