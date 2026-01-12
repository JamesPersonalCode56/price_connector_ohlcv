# Chapter 9 - Health Server and Metrics

Health server:
- /health and /ready endpoints for liveness and readiness.

Metrics:
- Prometheus counters and gauges in metrics.py
- Quote latency histogram, queue depth, reconnections, and errors

Note: metrics are recorded via MetricsCollector; ensure it is wired in during
stream processing if extended.
