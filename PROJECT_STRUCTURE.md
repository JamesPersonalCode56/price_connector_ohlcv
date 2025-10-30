# Project Structure

Complete directory structure and file organization for the OHLCV Python Connector.

---

##  Root Directory

```
ohlcv-python-connector/
├── README.md                    # Main project documentation
├── PROJECT_STRUCTURE.md         # This file
├── .env.example                 # Configuration template
├── .gitignore                   # Git ignore rules
├── requirements.txt             # Python dependencies (pip)
├── pyproject.toml               # Poetry configuration
├── poetry.lock                  # Dependency lock file
├── start.sh                     # Quick start script
├── test_imports.py              # Import validation script
│
├── docs/                        #  Documentation folder
├── src/                         #  Source code
└── test/                        #  Test files
```

---

##  Documentation (`/docs`)

All project documentation organized in one place:

```
docs/
├── README.md                    # Documentation index and navigation
├── QUICKSTART.md                # 5-minute setup guide
├── UPGRADE.md                   # Comprehensive feature guide
├── DEPLOYMENT_CHECKLIST.md      # Deployment procedures
├── IMPLEMENTATION_SUMMARY.md    # Technical implementation details
├── CHANGES.md                   # Version history and changelog
└── data_sources_and_mapping.md  # Exchange API reference
```

**Navigation:** Start with [docs/README.md](docs/README.md)

---

##  Source Code (`/src`)

Application source code following Clean Architecture:

```
src/
├── config.py                    # Configuration management
├── logging_config.py            # Logging setup
├── metrics.py                   # Metrics collection (Prometheus + logging)
│
├── domain/                      #  Core business layer
│   ├── __init__.py
│   ├── models.py                # PriceQuote entity
│   └── repositories.py          # Repository interfaces
│
├── application/                 #  Use cases layer
│   ├── __init__.py
│   └── use_cases/
│       ├── __init__.py
│       └── stream_prices.py     # StreamPrices use case
│
├── infrastructure/              #  Infrastructure layer
│   ├── __init__.py
│   │
│   ├── common/                  # Shared infrastructure
│   │   ├── __init__.py
│   │   ├── client.py            # Base WebSocket client
│   │   ├── client_backup.py     # Original client backup
│   │   ├── client_v2.py         # Enhanced client (reference)
│   │   ├── repository.py        # Base repository implementations
│   │   ├── circuit_breaker.py   # Circuit breaker pattern
│   │   ├── quote_queue.py       # Dual-pipeline queue system
│   │   ├── deduplicator.py      # Message deduplication
│   │   ├── rest_pool.py         # HTTP connection pooling
│   │   └── shutdown.py          # Graceful shutdown handler
│   │
│   ├── binance/                 # Binance exchange
│   │   ├── __init__.py
│   │   ├── client.py            # Binance WebSocket client
│   │   └── repositories.py      # Binance repository
│   │
│   ├── okx/                     # OKX exchange
│   │   ├── __init__.py
│   │   ├── client.py
│   │   └── repositories.py
│   │
│   ├── bybit/                   # Bybit exchange
│   │   ├── __init__.py
│   │   ├── client.py
│   │   └── repositories.py
│   │
│   ├── gateio/                  # Gate.io exchange
│   │   ├── __init__.py
│   │   ├── client.py
│   │   └── repositories.py
│   │
│   └── hyperliquid/             # Hyperliquid exchange
│       ├── __init__.py
│       ├── client.py
│       └── repositories.py
│
└── interfaces/                  #  Entry points layer
    ├── __init__.py
    ├── repository_factory.py    # Dependency injection factory
    ├── health_server.py         # HTTP health check server
    │
    ├── cli/                     # CLI interface
    │   ├── __init__.py
    │   └── main.py              # Command-line interface
    │
    └── ws_server/               # WebSocket server interface
        ├── __init__.py
        └── main.py              # WebSocket server
```

---

##  Tests (`/test`)

Integration and unit tests:

```
test/
├── run_all_ws_subscriptions.py  # Batch integration test
│
├── test_binance_btc_spot.py     # Binance spot test
├── test_binance_btc_um.py       # Binance USDT-M futures
├── test_binance_btc_cm.py       # Binance Coin-M futures
│
├── test_okx_btc_spot.py         # OKX spot test
├── test_okx_btc_swap.py         # OKX USDT-M perpetual
├── test_okx_btc_swap_coinm.py   # OKX Coin-M perpetual
│
├── test_bybit_btc_spot.py       # Bybit spot test
├── test_bybit_btc_linear.py     # Bybit linear perpetual
├── test_bybit_btc_inverse.py    # Bybit inverse perpetual
│
├── test_gateio_btc_spot.py      # Gate.io spot test
├── test_gateio_btc_um.py        # Gate.io USDT-M futures
├── test_gateio_btc_cm.py        # Gate.io Coin-M futures
│
├── test_hyperliquid_btc_usdm.py # Hyperliquid USDT-M
├── test_hyperliquid_btc_coinm.py# Hyperliquid Coin-M
└── test_hyperliquid_purr_spot.py# Hyperliquid spot
```

---

## ️ File Categories

### Configuration Files

| File | Purpose | Read More |
|------|---------|-----------|
| `.env.example` | Configuration template | [docs/UPGRADE.md](docs/UPGRADE.md#configuration) |
| `config.py` | Configuration loader | [docs/IMPLEMENTATION_SUMMARY.md](docs/IMPLEMENTATION_SUMMARY.md) |
| `pyproject.toml` | Poetry/project config | - |
| `requirements.txt` | pip dependencies | - |

### Core Infrastructure Files

| File | Lines | Purpose |
|------|-------|---------|
| `src/metrics.py` | ~400 | Prometheus + structured logging metrics |
| `src/infrastructure/common/circuit_breaker.py` | ~220 | Fault tolerance circuit breaker |
| `src/infrastructure/common/quote_queue.py` | ~160 | Dual-pipeline queue system |
| `src/infrastructure/common/deduplicator.py` | ~130 | Message deduplication |
| `src/infrastructure/common/rest_pool.py` | ~50 | HTTP connection pooling |
| `src/infrastructure/common/shutdown.py` | ~90 | Graceful shutdown |
| `src/interfaces/health_server.py` | ~200 | Health check HTTP server |

### Exchange Connectors

Each exchange has 2 files: `client.py` (WebSocket) and `repositories.py` (factory)

| Exchange | Client Lines | Notable Features |
|----------|--------------|------------------|
| Binance | 176 | Multiple contract types, combined streams |
| OKX | 190 | Flexible instrument types |
| Bybit | 214 | Custom ping/pong protocol |
| Gate.io | 410 | Most complex, multiple endpoints |
| Hyperliquid | 296 | Symbol mapping, POST requests |

### Documentation Files

| File | Lines | Purpose |
|------|-------|---------|
| `README.md` | ~500 | Main project documentation |
| `docs/README.md` | ~300 | Documentation index |
| `docs/QUICKSTART.md` | ~500 | Quick start guide |
| `docs/UPGRADE.md` | ~800 | Comprehensive feature guide |
| `docs/DEPLOYMENT_CHECKLIST.md` | ~600 | Deployment procedures |
| `docs/IMPLEMENTATION_SUMMARY.md` | ~500 | Technical details |
| `docs/CHANGES.md` | ~300 | Changelog |
| `docs/data_sources_and_mapping.md` | ~400 | Exchange API reference |

---

##  Key File Locations by Feature

### Circuit Breaker
- **Implementation:** `src/infrastructure/common/circuit_breaker.py`
- **Usage:** `src/infrastructure/common/client_v2.py` (reference)
- **Config:** `src/config.py` (lines 56-58)
- **Docs:** `docs/UPGRADE.md` (Fault Tolerance section)

### Dual-Pipeline Queue
- **Implementation:** `src/infrastructure/common/quote_queue.py`
- **Usage:** `src/infrastructure/common/client_v2.py` (reference)
- **Config:** `src/config.py` (lines 60-61)
- **Docs:** `docs/IMPLEMENTATION_SUMMARY.md` (Dual-Pipeline section)

### Metrics & Monitoring
- **Implementation:** `src/metrics.py`
- **Health Server:** `src/interfaces/health_server.py`
- **Integration:** `src/interfaces/ws_server/main.py` (lines 235-246)
- **Config:** `src/config.py` (lines 77-78)
- **Docs:** `docs/UPGRADE.md` (Monitoring section)

### Deduplication
- **Implementation:** `src/infrastructure/common/deduplicator.py`
- **Usage:** `src/infrastructure/common/client_v2.py` (reference)
- **Config:** `src/config.py` (lines 63-64)
- **Docs:** `docs/IMPLEMENTATION_SUMMARY.md`

### Connection Pooling
- **Implementation:** `src/infrastructure/common/rest_pool.py`
- **Usage Example:** `src/infrastructure/binance/client.py` (line 130)
- **Config:** `src/config.py` (lines 66-67)
- **Docs:** `docs/UPGRADE.md` (Performance section)

### Graceful Shutdown
- **Implementation:** `src/infrastructure/common/shutdown.py`
- **Integration:** `src/interfaces/ws_server/main.py` (lines 236-262)
- **Docs:** `docs/DEPLOYMENT_CHECKLIST.md`

---

##  Dependency Tree

### Production Dependencies
```
websockets>=12.0          # WebSocket client/server
httpx>=0.27               # Async HTTP client (with HTTP/2)
python-dotenv>=1.0        # Environment variables
orjson>=3.9.0             # Fast JSON parsing (optional but recommended)
prometheus-client>=0.19.0 # Metrics export
```

### Development Dependencies
```
ruff>=0.5.0               # Linting
mypy>=1.10.0              # Type checking
pytest>=8.1.0             # Testing
```

---

##  Finding Code

### By Feature

**Want to understand WebSocket connections?**
→ `src/infrastructure/common/client.py`

**Want to see circuit breaker logic?**
→ `src/infrastructure/common/circuit_breaker.py`

**Want to understand metrics?**
→ `src/metrics.py`

**Want to see an exchange implementation?**
→ `src/infrastructure/binance/client.py` (simplest)
→ `src/infrastructure/gateio/client.py` (most complex)

**Want to see health checks?**
→ `src/interfaces/health_server.py`

**Want to see WebSocket server?**
→ `src/interfaces/ws_server/main.py`

### By Exchange

Each exchange has the same structure:

```
src/infrastructure/<exchange>/
├── client.py          # WebSocket client + REST client
└── repositories.py    # Repository factory
```

All extend the base classes from `src/infrastructure/common/`

---

##  Entry Points

The application has 3 entry points:

### 1. CLI (`src/interfaces/cli/main.py`)
```bash
poetry run connector-cli <exchange> <symbols...> [options]
```

### 2. WebSocket Server (`src/interfaces/ws_server/main.py`)
```bash
poetry run connector-wss [--host HOST] [--port PORT]
```

### 3. Health Check Server (`src/interfaces/health_server.py`)
Automatically starts with WebSocket server on port 8766

---

##  Code Statistics

### Total Lines of Code

| Category | Files | Lines |
|----------|-------|-------|
| Source Code | ~30 | ~3,500 |
| Tests | 15 | ~800 |
| Documentation | 8 | ~4,000 |
| Configuration | 4 | ~200 |
| **Total** | **~57** | **~8,500** |

### Language Breakdown

- Python: 95%
- Markdown: 4%
- Shell: 1%

---

##  Version Control

### Git Structure

```
.git/                    # Git repository
.gitignore              # Ignored files
```

### Important Branches

- `main` / `master` - Stable production code
- Feature branches as needed

---

##  Learning the Codebase

### Recommended Reading Order

1. **Start:** `README.md` - Project overview
2. **Core Domain:** `src/domain/models.py` - Understand PriceQuote
3. **Base Client:** `src/infrastructure/common/client.py` - Core logic
4. **Example Exchange:** `src/infrastructure/binance/client.py` - Concrete implementation
5. **Entry Point:** `src/interfaces/ws_server/main.py` - How it all connects
6. **New Features:** Files in `src/infrastructure/common/` - Enhancements

### Code Exploration Tips

1. **Start with interfaces** (`src/interfaces/`) to understand entry points
2. **Read domain models** (`src/domain/`) to understand data structures
3. **Study base classes** (`src/infrastructure/common/`) to understand patterns
4. **Pick one exchange** to understand concrete implementation
5. **Follow the data flow** from WebSocket → Circuit Breaker → Dedup → Queue → Consumer

---

##  Maintenance

### Adding a New Exchange

1. Create `src/infrastructure/<exchange>/` directory
2. Implement `client.py` extending `WebSocketPriceFeedClient`
3. Implement `repositories.py` with factory function
4. Register in `src/interfaces/repository_factory.py`
5. Add tests in `test/`
6. Update `docs/data_sources_and_mapping.md`

### Adding a New Feature

1. Implement in appropriate layer (domain/application/infrastructure)
2. Add configuration in `src/config.py` if needed
3. Add tests
4. Update documentation in `docs/`
5. Add entry in `docs/CHANGES.md`

---

##  Cross-References

- **Main README** → [README.md](README.md)
- **Documentation Index** → [docs/README.md](docs/README.md)
- **Quick Start** → [docs/QUICKSTART.md](docs/QUICKSTART.md)
- **Configuration** → [.env.example](.env.example)

---

**Version:** 0.2.0
**Last Updated:** 2024-10-30
**Total Files:** ~57
**Total Lines:** ~8,500

---

[ View Documentation](docs/) | [ Read Main README](README.md)
