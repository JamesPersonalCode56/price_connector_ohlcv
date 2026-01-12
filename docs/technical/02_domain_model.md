# Chapter 2 - Domain Model

Primary entity:
- PriceQuote: normalized OHLCV candle payload with timestamps and metadata

Repository abstraction:
- PriceFeedRepository defines stream_quotes(symbols) -> AsyncIterator[PriceQuote]
