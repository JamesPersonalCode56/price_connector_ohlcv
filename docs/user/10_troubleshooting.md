# Chapter 10 - Troubleshooting

Common errors and causes:
- WS_PROTOCOL_ERROR: invalid JSON or invalid payload type.
- WS_SUBSCRIBE_REJECTED: invalid payload fields.
- WS_CONNECT_FAILED: upstream exchange connection failed.
- WS_STREAM_TIMEOUT: no data received within timeout window.
- RATE_LIMITED: upstream exchange rate limit hit.
- REST_BACKFILL_FAILED: REST backfill failed during idle.

Suggested actions:
- Validate the payload format and symbols.
- Reduce concurrency or batch size to avoid rate limits.
- Increase timeouts for illiquid instruments.
- Check logs and /metrics for connection error spikes.
