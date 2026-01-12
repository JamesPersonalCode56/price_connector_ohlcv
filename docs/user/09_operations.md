# Chapter 9 - Operational Guidance

- If you expect slow or illiquid symbols, increase CONNECTOR_STREAM_IDLE_TIMEOUT.
- If you subscribe to many symbols, increase CONNECTOR_MAX_SYMBOL_PER_WS or
  reduce client batch sizes.
- If the server uses too much memory, limit queue sizes and reduce max connections.
