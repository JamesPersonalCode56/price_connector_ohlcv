# Chapter 8 - WebSocket Server

Interfaces:
- The server accepts a single JSON subscription per client.
- It returns a subscribed confirmation message.
- Then it streams kline events via to_kline_event.

Error mapping:
- Input validation errors -> WS_SUBSCRIBE_REJECTED
- Connection failures -> WS_CONNECT_FAILED
- SubscriptionError -> mapped to RATE_LIMITED, INVALID_SYMBOL, REST_BACKFILL_FAILED
- Timeout -> WS_STREAM_TIMEOUT
- Queue overflow -> INTERNAL_QUEUE_BACKPRESSURE
