# Chapter 11 - Load Testing

Use the load test script to verify all subscriptions:
- tests/load/run_all_ws_subscriptions.py

This script discovers instruments via REST APIs and then subscribes in batches to
your local server. Run with defaults or provide batch size, concurrency, and
timeouts if required.
