from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class KlineCandle:
    t: int
    T: int
    s: str
    i: str
    o: float
    c: float
    h: float
    l: float
    v: float
    x: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "t": self.t,
            "T": self.T,
            "s": self.s,
            "i": self.i,
            "o": self.o,
            "c": self.c,
            "h": self.h,
            "l": self.l,
            "v": self.v,
            "x": self.x,
        }


@dataclass(frozen=True)
class KlineEvent:
    e: str
    E: int
    s: str
    k: KlineCandle

    def to_dict(self) -> dict[str, object]:
        return {
            "e": self.e,
            "E": self.E,
            "s": self.s,
            "k": self.k.to_dict(),
        }


@dataclass(frozen=True)
class PriceQuote:
    exchange: str
    symbol: str
    contract_type: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_num: int
    is_closed_candle: bool

    def to_kline_event(
        self, event_time: datetime | None = None, interval: str = "1m"
    ) -> dict[str, object]:
        """Convert the quote to a Binance-like kline event payload."""
        event_dt = event_time or datetime.now(timezone.utc)
        start_ms = int(self.timestamp.timestamp() * 1000)
        close_ms = start_ms
        candle = KlineCandle(
            t=start_ms,
            T=close_ms,
            s=self.symbol,
            i=interval,
            o=self.open,
            c=self.close,
            h=self.high,
            l=self.low,
            v=self.volume,
            x=self.is_closed_candle,
        )
        event = KlineEvent(
            e="kline",
            E=int(event_dt.timestamp() * 1000),
            s=self.symbol,
            k=candle,
        )
        return event.to_dict()
