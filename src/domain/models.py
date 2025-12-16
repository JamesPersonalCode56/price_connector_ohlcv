from dataclasses import dataclass
from datetime import datetime


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
