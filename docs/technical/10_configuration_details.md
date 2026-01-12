# Chapter 10 - Configuration Details

Settings are loaded in config.py from environment variables. Key sections:
- connector: timeouts, reconnection delay, queue sizes, dedup config
- ws_server: host, port, log level, subscribe timeout

Defaults are safe but not optimal for all workloads. Tune per exchange and
subscription count.
