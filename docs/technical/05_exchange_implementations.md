# Chapter 5 - Exchange Implementations

Each exchange implements:
- Configuration object with base URL and interval mapping.
- _build_connection_args and _process_message.
- Optional REST backfill via httpx.

Parsing notes:
- JSON parsing uses orjson when available.
- Messages are converted to PriceQuote with normalized timestamp and floats.
