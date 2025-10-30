# Quick Start Guide - v0.2.0

##  5-Minute Setup

### 1. Install Dependencies

```bash
# Option A: pip
pip install -r requirements.txt

# Option B: Poetry (recommended)
poetry install
```

### 2. Configure (Optional - has defaults)

```bash
cp .env.example .env
# Edit .env if you want to customize settings
```

### 3. Start the WebSocket Server

```bash
poetry run connector-wss
```

You'll see:
```
INFO - Starting WebSocket server host=0.0.0.0 port=8765
INFO - Health check server started host=0.0.0.0 port=8766
INFO - WebSocket server ready to accept connections
```

### 4. Verify It's Running

```bash
# Check health
curl http://localhost:8766/health

# Check readiness
curl http://localhost:8766/ready

# Get metrics
curl http://localhost:8766/metrics
```

### 5. Connect a Client

```bash
# In another terminal, test with websocat or your client
echo '{"exchange":"binance","contract_type":"spot","symbols":["BTCUSDT"],"limit":5}' | websocat ws://localhost:8765
```

---

##  Quick Monitoring Setup

### Using Prometheus

1. Add to `prometheus.yml`:
```yaml
scrape_configs:
  - job_name: 'ohlcv'
    static_configs:
      - targets: ['localhost:8766']
```

2. Start Prometheus:
```bash
prometheus --config.file=prometheus.yml
```

3. Query metrics at `http://localhost:9090`

### Key Metrics to Watch

```promql
# Quotes per second
rate(connector_quotes_processed_total[1m])

# 95th percentile latency
histogram_quantile(0.95, rate(connector_quote_latency_seconds_bucket[5m]))

# Active connections
connector_active_connections

# Circuit breaker status (should be 0)
connector_circuit_breaker_state

# Queue depth
connector_queue_depth_closed
```

---

##  Docker Quick Start

### Build

```bash
docker build -t ohlcv-connector:latest .
```

### Run

```bash
docker run -p 8765:8765 -p 8766:8766 \
  -e CONNECTOR_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5 \
  -e CONNECTOR_CLOSED_QUEUE_MAXSIZE=1000 \
  ohlcv-connector:latest
```

### Docker Compose

```yaml
version: '3.8'
services:
  connector:
    build: .
    ports:
      - "8765:8765"
      - "8766:8766"
    environment:
      - CONNECTOR_LOG_LEVEL=INFO
      - CONNECTOR_WSS_HEALTH_CHECK_ENABLED=true
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8766/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

---

##  Kubernetes Quick Start

### Deploy

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ohlcv-connector
spec:
  replicas: 2
  selector:
    matchLabels:
      app: ohlcv-connector
  template:
    metadata:
      labels:
        app: ohlcv-connector
    spec:
      containers:
      - name: connector
        image: ohlcv-connector:latest
        ports:
        - containerPort: 8765
          name: websocket
        - containerPort: 8766
          name: health
        env:
        - name: CONNECTOR_WSS_HEALTH_CHECK_ENABLED
          value: "true"
        - name: CONNECTOR_CLOSED_QUEUE_MAXSIZE
          value: "1000"
        livenessProbe:
          httpGet:
            path: /health
            port: 8766
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /ready
            port: 8766
          initialDelaySeconds: 5
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: ohlcv-connector
spec:
  selector:
    app: ohlcv-connector
  ports:
  - name: websocket
    port: 8765
    targetPort: 8765
  - name: health
    port: 8766
    targetPort: 8766
```

### Apply

```bash
kubectl apply -f deployment.yaml
```

### Check Status

```bash
# Check pods
kubectl get pods -l app=ohlcv-connector

# Check health
kubectl port-forward svc/ohlcv-connector 8766:8766
curl http://localhost:8766/ready
```

---

##  Common Configuration Scenarios

### High-Load Configuration (1000+ symbols)

```.env
# Increase queue size
CONNECTOR_CLOSED_QUEUE_MAXSIZE=2000
CONNECTOR_OPEN_QUEUE_MAXSIZE=10000

# More connections per WS
CONNECTOR_MAX_SYMBOL_PER_WS=100

# Larger REST pool
CONNECTOR_REST_POOL_MAXSIZE=50
CONNECTOR_REST_POOL_CONNECTIONS=20

# More aggressive circuit breaker
CONNECTOR_CIRCUIT_BREAKER_FAILURE_THRESHOLD=3
CONNECTOR_CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60.0
```

### Low-Latency Configuration

```.env
# Smaller queues for faster processing
CONNECTOR_CLOSED_QUEUE_MAXSIZE=100

# Faster inactivity timeout
CONNECTOR_INACTIVITY_TIMEOUT=1.0

# More frequent pings
CONNECTOR_WS_PING_INTERVAL=10.0
```

### Memory-Constrained Environment

```.env
# Smaller queues
CONNECTOR_CLOSED_QUEUE_MAXSIZE=500
CONNECTOR_OPEN_QUEUE_MAXSIZE=2000

# Smaller dedup cache
CONNECTOR_DEDUPLICATION_MAX_ENTRIES=5000
CONNECTOR_DEDUPLICATION_WINDOW_SECONDS=60.0

# Fewer symbols per connection
CONNECTOR_MAX_SYMBOL_PER_WS=25
```

---

##  Testing

### Run Unit Tests

```bash
poetry run pytest
```

### Test Specific Exchange

```bash
poetry run python test/test_binance_btc_spot.py
```

### Batch Test All Exchanges

```bash
poetry run python test/run_all_ws_subscriptions.py \
  --batch-size 50 \
  --limit 10 \
  --concurrency 5
```

---

##  Performance Tuning Tips

1. **Start with defaults** - They work for most cases

2. **Monitor first** - Watch metrics before tuning

3. **Tune incrementally** - Change one thing at a time

4. **Key indicators:**
   - `connector_queue_blocking_events_total` > 0 → Increase queue size
   - `connector_circuit_breaker_state` = 1 → Check exchange connectivity
   - `connector_quote_latency_seconds` P95 > 1s → Increase REST pool size
   - Memory growing → Set `CONNECTOR_OPEN_QUEUE_MAXSIZE`

5. **Horizontal scaling** - Run multiple instances behind load balancer

---

##  Troubleshooting

### Server Won't Start

```bash
# Check if ports are in use
lsof -i:8765
lsof -i:8766

# Check logs
poetry run connector-wss --log-level DEBUG
```

### No Quotes Received

1. Check health endpoint:
   ```bash
   curl http://localhost:8766/ready
   ```

2. Check circuit breaker state in metrics:
   ```bash
   curl http://localhost:8766/metrics | grep circuit_breaker_state
   ```

3. Test exchange connectivity:
   ```bash
   curl https://api.binance.com/api/v3/exchangeInfo
   ```

### High Memory Usage

1. Check queue depths:
   ```bash
   curl http://localhost:8766/metrics | grep queue_depth
   ```

2. Set queue limits:
   ```.env
   CONNECTOR_OPEN_QUEUE_MAXSIZE=5000
   ```

3. Reduce symbols per connection:
   ```.env
   CONNECTOR_MAX_SYMBOL_PER_WS=25
   ```

---

##  Next Steps

- Read [UPGRADE.md](UPGRADE.md) for detailed feature explanations
- Check [docs/data_sources_and_mapping.md](docs/data_sources_and_mapping.md) for exchange details
- Review [CHANGES.md](CHANGES.md) for complete changelog
- Set up Grafana dashboards for visualization

---

##  Pro Tips

1. **Always enable health checks in production:**
   ```bash
   CONNECTOR_WSS_HEALTH_CHECK_ENABLED=true
   ```

2. **Use orjson for better performance:**
   ```bash
   pip install orjson  # 2-5x faster JSON parsing
   ```

3. **Monitor circuit breaker state:**
   - Alert when `circuit_breaker_state != 0`

4. **Set alerts on queue blocking:**
   - Alert when `rate(connector_queue_blocking_events_total[5m]) > 0`

5. **Test graceful shutdown:**
   ```bash
   kill -TERM $(pgrep -f connector-wss)
   # Check logs for "Server shutdown complete"
   ```

---

**Need help?** Open an issue or check the full documentation in [UPGRADE.md](UPGRADE.md)
