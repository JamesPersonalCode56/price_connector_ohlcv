# Deployment Checklist - v0.2.0

Use this checklist to ensure smooth deployment of the upgraded connector.

---

## Pre-Deployment

### 1. Environment Preparation

- [ ] **Install Dependencies**
  ```bash
  cd /home/minh/main/execution_service/server_v2/ohlcv-python-connector
  pip install -r requirements.txt
  # or
  poetry install
  ```

- [ ] **Verify Installation**
  ```bash
  python3 -c "import orjson; import prometheus_client; print(' Dependencies OK')"
  ```

- [ ] **Configure Environment**
  ```bash
  cp .env.example .env
  # Edit .env with your settings
  nano .env
  ```

- [ ] **Validate Configuration**
  ```bash
  PYTHONPATH=src python3 -c "from config import SETTINGS; print(f' Config loaded: {SETTINGS.connector.closed_queue_maxsize}')"
  ```

### 2. Pre-Flight Tests

- [ ] **Test Health Server**
  ```bash
  # Terminal 1: Start server
  poetry run connector-wss

  # Terminal 2: Test endpoints
  curl http://localhost:8766/health
  curl http://localhost:8766/ready
  curl http://localhost:8766/metrics | head -20
  ```

- [ ] **Test WebSocket Connection**
  ```bash
  # Install websocat if needed: cargo install websocat
  echo '{"exchange":"binance","contract_type":"spot","symbols":["BTCUSDT"],"limit":3}' | \
    websocat ws://localhost:8765
  ```

- [ ] **Test Graceful Shutdown**
  ```bash
  # Start server
  poetry run connector-wss &
  SERVER_PID=$!

  # Wait a bit
  sleep 5

  # Send SIGTERM
  kill -TERM $SERVER_PID

  # Check logs for "Server shutdown complete"
  ```

- [ ] **Run Integration Tests**
  ```bash
  poetry run python test/test_binance_btc_spot.py
  ```

---

## Deployment Steps

### Option 1: Direct Upgrade (Simple)

- [ ] **Step 1: Backup Current Version**
  ```bash
  # Backup the entire directory
  cp -r ohlcv-python-connector ohlcv-python-connector.backup
  ```

- [ ] **Step 2: Stop Current Service**
  ```bash
  # Find process
  ps aux | grep connector-wss

  # Kill gracefully
  kill -TERM <PID>

  # Or if using systemd
  sudo systemctl stop ohlcv-connector
  ```

- [ ] **Step 3: Update Code**
  ```bash
  cd ohlcv-python-connector
  git pull  # or copy new files
  pip install -r requirements.txt
  ```

- [ ] **Step 4: Update Configuration**
  ```bash
  # Merge new settings from .env.example
  diff .env .env.example
  # Add any new settings you want to customize
  ```

- [ ] **Step 5: Start New Version**
  ```bash
  poetry run connector-wss

  # Or if using systemd
  sudo systemctl start ohlcv-connector
  ```

- [ ] **Step 6: Verify Operation**
  ```bash
  # Check health
  curl http://localhost:8766/health

  # Check logs
  tail -f logs/connector.log

  # Check metrics
  curl http://localhost:8766/metrics | grep connector_active_connections
  ```

### Option 2: Blue-Green Deployment (Zero Downtime)

- [ ] **Step 1: Deploy Green (New Version)**
  ```bash
  # Deploy to different ports
  export CONNECTOR_WSS_PORT=8767
  export CONNECTOR_WSS_HEALTH_CHECK_PORT=8768
  poetry run connector-wss &
  GREEN_PID=$!
  ```

- [ ] **Step 2: Verify Green Health**
  ```bash
  curl http://localhost:8768/ready
  # Ensure status is "ready"
  ```

- [ ] **Step 3: Smoke Test Green**
  ```bash
  echo '{"exchange":"binance","contract_type":"spot","symbols":["BTCUSDT"],"limit":1}' | \
    websocat ws://localhost:8767
  ```

- [ ] **Step 4: Switch Load Balancer**
  ```bash
  # Update your load balancer/nginx/haproxy to point to port 8767
  # Or update Kubernetes service
  kubectl patch service ohlcv-connector -p '{"spec":{"selector":{"version":"v0.2.0"}}}'
  ```

- [ ] **Step 5: Monitor for Issues**
  ```bash
  # Watch metrics
  watch -n 5 'curl -s http://localhost:8768/metrics | grep _total'

  # Monitor logs
  tail -f logs/connector.log
  ```

- [ ] **Step 6: Decommission Blue (Old Version)**
  ```bash
  # After 30 minutes of stable operation
  kill -TERM <BLUE_PID>
  ```

### Option 3: Kubernetes Rolling Update

- [ ] **Step 1: Update Deployment YAML**
  ```yaml
  spec:
    template:
      metadata:
        labels:
          version: v0.2.0
      spec:
        containers:
        - name: connector
          image: ohlcv-connector:0.2.0
          env:
          - name: CONNECTOR_WSS_HEALTH_CHECK_ENABLED
            value: "true"
  ```

- [ ] **Step 2: Apply Update**
  ```bash
  kubectl apply -f deployment.yaml
  ```

- [ ] **Step 3: Watch Rollout**
  ```bash
  kubectl rollout status deployment/ohlcv-connector
  ```

- [ ] **Step 4: Verify Pods**
  ```bash
  kubectl get pods -l app=ohlcv-connector
  kubectl logs -l app=ohlcv-connector -f
  ```

- [ ] **Step 5: Check Health**
  ```bash
  kubectl port-forward svc/ohlcv-connector 8766:8766
  curl http://localhost:8766/ready
  ```

---

## Post-Deployment Verification

### Immediate Checks (0-5 minutes)

- [ ] **Health Endpoints Responding**
  ```bash
  curl http://localhost:8766/health
  # Expected: {"status":"healthy",...}
  ```

- [ ] **WebSocket Server Accepting Connections**
  ```bash
  echo '{"exchange":"binance","contract_type":"spot","symbols":["BTCUSDT"],"limit":1}' | \
    websocat ws://localhost:8765
  # Expected: Quote received
  ```

- [ ] **Metrics Being Collected**
  ```bash
  curl http://localhost:8766/metrics | grep connector_quotes_processed_total
  # Expected: Non-zero count
  ```

- [ ] **No Errors in Logs**
  ```bash
  tail -100 logs/connector.log | grep ERROR
  # Expected: No critical errors
  ```

### Short-Term Monitoring (5-30 minutes)

- [ ] **Quotes Flowing**
  ```bash
  # Check quote rate
  curl -s http://localhost:8766/metrics | grep connector_quotes_processed_total
  # Wait 60 seconds
  curl -s http://localhost:8766/metrics | grep connector_quotes_processed_total
  # Rate should increase
  ```

- [ ] **No Circuit Breakers Open**
  ```bash
  curl -s http://localhost:8766/metrics | grep connector_circuit_breaker_state
  # All values should be 0
  ```

- [ ] **No Queue Blocking**
  ```bash
  curl -s http://localhost:8766/metrics | grep connector_queue_blocking_events_total
  # Should be 0 or very low
  ```

- [ ] **Active Connections Stable**
  ```bash
  curl -s http://localhost:8766/metrics | grep connector_active_connections
  # Should match expected exchange count
  ```

- [ ] **Memory Usage Stable**
  ```bash
  ps aux | grep connector-wss
  # Note RSS (memory) value, check again in 30 min
  ```

### Long-Term Monitoring (1+ hours)

- [ ] **No Memory Leaks**
  ```bash
  # Memory should plateau, not grow linearly
  watch -n 300 'ps aux | grep connector-wss'
  ```

- [ ] **Latency Acceptable**
  ```bash
  curl -s http://localhost:8766/metrics | grep connector_quote_latency_seconds
  # P95 should be < 1 second
  ```

- [ ] **No Duplicate Spikes**
  ```bash
  curl -s http://localhost:8766/metrics | grep connector_duplicates_filtered_total
  # Rate should be very low (<1%)
  ```

- [ ] **REST Backfills Working**
  ```bash
  curl -s http://localhost:8766/metrics | grep connector_rest_backfills_total
  # Success rate should be >95%
  ```

---

## Monitoring Setup

### Prometheus

- [ ] **Add Scrape Target**
  ```yaml
  # prometheus.yml
  scrape_configs:
    - job_name: 'ohlcv-connector'
      static_configs:
        - targets: ['localhost:8766']
      scrape_interval: 15s
  ```

- [ ] **Reload Prometheus**
  ```bash
  curl -X POST http://localhost:9090/-/reload
  ```

- [ ] **Verify Scraping**
  ```bash
  # Check Prometheus UI
  # Navigate to Status > Targets
  # Ensure ohlcv-connector is UP
  ```

### Alerts (Recommended)

- [ ] **Configure Critical Alerts**
  ```yaml
  groups:
  - name: ohlcv-connector
    rules:
    - alert: ConnectorDown
      expr: up{job="ohlcv-connector"} == 0
      for: 1m
      annotations:
        summary: "Connector is down"

    - alert: CircuitBreakerOpen
      expr: connector_circuit_breaker_state > 0
      for: 2m
      annotations:
        summary: "Circuit breaker open for {{ $labels.exchange }}"

    - alert: HighQueueDepth
      expr: connector_queue_depth_closed > 800
      for: 5m
      annotations:
        summary: "Queue depth critical (>80% full)"

    - alert: HighLatency
      expr: histogram_quantile(0.95, rate(connector_quote_latency_seconds_bucket[5m])) > 2
      for: 5m
      annotations:
        summary: "High quote latency (P95 > 2s)"
  ```

### Grafana Dashboard (Optional)

- [ ] **Create Dashboard**
  - Panel 1: Quote rate (rate(connector_quotes_processed_total[1m]))
  - Panel 2: Active connections (connector_active_connections)
  - Panel 3: Latency (histogram_quantile)
  - Panel 4: Queue depths (connector_queue_depth_*)
  - Panel 5: Error rate (rate(connector_connection_errors_total[5m]))
  - Panel 6: Circuit breaker states (connector_circuit_breaker_state)

---

## Rollback Procedure

If issues arise:

### Quick Rollback

- [ ] **Step 1: Stop New Version**
  ```bash
  kill -TERM <NEW_PID>
  # Or
  sudo systemctl stop ohlcv-connector
  ```

- [ ] **Step 2: Start Old Version**
  ```bash
  cd ohlcv-python-connector.backup
  poetry run connector-wss &
  ```

- [ ] **Step 3: Verify**
  ```bash
  # Check old version is working
  curl http://localhost:8765  # Should respond
  ```

### Kubernetes Rollback

- [ ] **Rollback Deployment**
  ```bash
  kubectl rollout undo deployment/ohlcv-connector
  kubectl rollout status deployment/ohlcv-connector
  ```

---

## Troubleshooting

### Common Issues

**Issue: Health endpoint not responding**
```bash
# Check if port is in use
lsof -i:8766

# Check if health checks are enabled
grep HEALTH_CHECK_ENABLED .env

# Check logs
tail -100 logs/connector.log | grep -i health
```

**Issue: High memory usage**
```bash
# Check queue metrics
curl http://localhost:8766/metrics | grep queue_depth

# Reduce queue size in .env
CONNECTOR_CLOSED_QUEUE_MAXSIZE=500
CONNECTOR_OPEN_QUEUE_MAXSIZE=2000

# Restart
```

**Issue: Circuit breaker stuck open**
```bash
# Check exchange connectivity
curl https://api.binance.com/api/v3/time

# Check metrics
curl http://localhost:8766/metrics | grep circuit_breaker

# May need to increase recovery timeout
CONNECTOR_CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60.0
```

---

## Success Criteria

Deployment is successful when ALL of these are true:

 Health endpoint returns 200
 Ready endpoint returns 200 with healthy exchanges
 Metrics endpoint returns Prometheus format
 WebSocket connections working
 Quote processing rate > 0
 No circuit breakers open
 Memory usage stable
 No critical errors in logs
 Graceful shutdown works
 All monitored metrics within thresholds

---

## Post-Deployment Tasks

- [ ] Update runbooks with new endpoints
- [ ] Train team on new monitoring
- [ ] Document any custom configurations
- [ ] Schedule performance review (1 week)
- [ ] Plan for next iteration improvements

---

**Deployment Date:** _______________
**Deployed By:** _______________
**Version:** 0.2.0
**Environment:**  Development  Staging  Production
**Status:**  Success  Rolled Back  In Progress
