# Chapter 13 - Performance Notes

Hot paths:
- JSON parsing and numeric conversions in exchange clients.
- Subscriber fan-out when many clients are connected.
- WebSocket send throughput on the server.

Potential optimizations:
- Use orjson and avoid intermediate structures.
- Limit subscriber queue sizes to control memory.
- Reduce batch size to avoid large combined subscriptions.
