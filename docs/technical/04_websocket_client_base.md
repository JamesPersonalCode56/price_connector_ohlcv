# Chapter 4 - WebSocket Client Base

WebSocketPriceFeedClient provides shared behaviors:
- Subscription symbol chunking to respect exchange limits.
- Single or multi-connection streaming with fan-in queue.
- Reconnect loop with backoff and error handling.
- Inactivity detection and optional REST backfill.

Key behaviors:
- _message_loop uses asyncio.wait_for with inactivity_timeout.
- On timeout, triggers _on_inactivity and then reconnects.
- SubscriptionError surfaces to caller to map error codes.
