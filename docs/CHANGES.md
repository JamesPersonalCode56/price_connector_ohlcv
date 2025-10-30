# Changelog

## [0.2.0] - 2024-10-30

###  Major Release: Production-Ready Enhancements

This release transforms the connector from a demo/prototype into a production-grade system suitable for high-load business scenarios.

---

###  Added

#### Core Infrastructure
- **Dual-pipeline queue system** (`src/infrastructure/common/quote_queue.py`)
  - Closed candles → Bounded queue with backpressure
  - Open candles → Unbounded LIFO stack
  - Prevents memory exhaustion
  - Observable metrics for queue depths and blocking events

- **Circuit breaker pattern** (`src/infrastructure/common/circuit_breaker.py`)
  - Exponential backoff (30s → 60s → 120s → 300s max)
  - Three states: CLOSED, OPEN, HALF_OPEN
  - Per-connection fault isolation
  - Configurable failure thresholds

- **Message deduplication** (`src/infrastructure/common/deduplicator.py`)
  - Symbol + timestamp based deduplication
  - 120-second sliding window (configurable)
  - Automatic cleanup of old entries
  - Prevents duplicate processing during reconnections

#### Observability & Monitoring
- **Metrics collection system** (`src/metrics.py`)
  - Prometheus-compatible metrics export
  - Structured logging with parseable fields
  - Tracked metrics:
    - Quote processing rates and latency
    - Active connection counts
    - Error rates by type
    - Queue depths and blocking events
    - Circuit breaker states
    - Duplicate detection counts

- **HTTP health check server** (`src/interfaces/health_server.py`)
  - Three endpoints:
    - `GET /health` - Liveness check
    - `GET /ready` - Readiness with exchange health
    - `GET /metrics` - Prometheus metrics
  - Kubernetes/Docker compatible
  - Configurable port (default: 8766)

#### Performance Optimizations
- **Connection pooling for REST clients** (`src/infrastructure/common/rest_pool.py`)
  - Reuses HTTP connections across requests
  - HTTP/2 support enabled
  - Configurable pool sizes
  - Significant performance improvement for backfill operations

- **Fast JSON parsing with orjson**
  - 2-5x faster than standard library
  - Graceful fallback to standard `json` if not available
  - Integrated throughout codebase

#### Operational Excellence
- **Graceful shutdown handler** (`src/infrastructure/common/shutdown.py`)
  - SIGTERM/SIGINT signal handling
  - Cleanup callback system
  - Connection draining
  - Kubernetes-ready

#### Configuration
- **Extended configuration system** (`src/config.py`)
  - 11 new configuration parameters
  - All with sensible defaults
  - Environment variable based
  - Documented in `.env.example`

###  Changed

#### Modified Files
- `src/infrastructure/binance/client.py`
  - Integrated connection pooling
  - Added orjson support
  - No breaking changes

- `src/interfaces/ws_server/main.py`
  - Integrated health check server
  - Added graceful shutdown
  - Integrated orjson for faster JSON processing
  - No breaking changes to API

- `src/config.py`
  - Added circuit breaker settings
  - Added queue management settings
  - Added deduplication settings
  - Added connection pool settings
  - Added health check settings
  - All backward compatible

- `.env.example`
  - Added documentation for all new settings
  - Organized into logical groups
  - Clear comments for each parameter

#### Enhanced Files
- `requirements.txt` - Added `orjson` and `prometheus-client`
- `pyproject.toml` - Added new dependencies
- `src/infrastructure/common/__init__.py` - Export new components

###  Documentation

- **NEW:** `UPGRADE.md` - Comprehensive upgrade guide
  - Configuration reference
  - Kubernetes integration examples
  - Docker Compose examples
  - Prometheus integration guide
  - Troubleshooting section
  - Performance benchmarks
  - Best practices

- **NEW:** `CHANGES.md` (this file) - Detailed changelog

###  Fixed

- Memory leaks from unbounded queues
- Duplicate message processing during reconnections
- Inefficient REST API connection usage
- No circuit breaker for failing exchanges
- Missing operational readiness indicators
- No graceful shutdown support

###  Migration

**Fully backward compatible!** No code changes required.

Steps:
1. Update dependencies: `pip install -r requirements.txt`
2. Optionally copy new env vars from `.env.example`
3. Restart services
4. Verify health endpoints: `curl http://localhost:8766/health`

---

## [0.1.0] - 2024-10-25

### Initial Release

- Clean Architecture implementation
- Support for 5 exchanges (Binance, OKX, Bybit, Gate.io, Hyperliquid)
- WebSocket streaming with automatic reconnection
- REST API backfill on inactivity
- CLI and WebSocket server interfaces
- Basic configuration via environment variables

---

## Version Numbering

We follow [Semantic Versioning](https://semver.org/):
- **MAJOR** version for incompatible API changes
- **MINOR** version for new functionality (backward compatible)
- **PATCH** version for backward compatible bug fixes

---

## Upgrade Path

- `0.1.x` → `0.2.x`: Seamless, no breaking changes
- Future `0.2.x` → `0.3.x`: Will maintain compatibility
- Future `0.x.x` → `1.0.0`: May include breaking changes (will be documented)
