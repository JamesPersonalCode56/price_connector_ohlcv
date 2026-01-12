# Chapter 12 - Load Testing

tests/load/run_all_ws_subscriptions.py:
- Discovers symbols via REST per exchange.
- Subscribes in batches to a local WebSocket server.
- Prints first quote per batch; reports timeouts.

Use parameters to tune:
- --batch-size
- --limit
- --concurrency
- --message-timeout
