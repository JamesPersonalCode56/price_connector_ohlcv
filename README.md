# OHLCV Python Connector

Stream 1-minute OHLCV candles from multiple crypto exchanges via a local WebSocket server.
The project uses a Clean Architecture layout and provides health and metrics endpoints
for production use.

Documentation
- User guide: docs/user/ (chaptered Markdown files)
- Technical docs: docs/technical/ (architecture and internals)
- Error cases: docs/test_cases/

Quick pointer
- Start server: poetry run connector-wss --host 0.0.0.0 --port 8765
- Health/metrics: http://localhost:8766/health, /ready, /metrics

For full setup, configuration, and usage examples, read the docs directories above.
