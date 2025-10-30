# Crypto Connector Clean Architecture
Ví dụ này minh họa cách tổ chức code theo clean architecture cho các connector WebSocket của nhiều sàn (Binance, OKX, Bybit, Gate.io, Bitget). Mỗi layer giữ trách nhiệm rõ ràng:

- `domain/`: mô tả entity (`PriceQuote`) và repository interface (`PriceFeedRepository`).
- `application/`: chứa use-case (`StreamPrices`) cung cấp luồng dữ liệu từ repository.
- `infrastructure/`: hiện thực từng exchange connector, ánh xạ dữ liệu raw -> domain model, tự động reconnect nếu quá 3s không nhận update và backfill bằng REST API.
- `interfaces/`: các entrypoint (CLI, WebSocket server) nhận tham số, gọi use-case và expose dữ liệu.

## Chạy bằng venv tiêu chuẩn

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src python -m interfaces.cli.main binance BTCUSDT ETHUSDT --market spot --limit 5
```

## Cấu hình

- Sao chép `.env.example` thành `.env` rồi điều chỉnh giá trị theo nhu cầu.
- Các biến chính:
  - `CONNECTOR_INACTIVITY_TIMEOUT`: số giây chờ WS trước khi backfill/restream (mặc định 3).
  - `CONNECTOR_RECONNECT_DELAY`: độ trễ giữa hai lần reconnect (mặc định 1).
  - `CONNECTOR_REST_TIMEOUT`: timeout khi gọi REST backfill (mặc định 5).
  - `CONNECTOR_WS_PING_INTERVAL` / `CONNECTOR_WS_PING_TIMEOUT`: cấu hình keep-alive cho mọi websocket out-bound (mặc định 20).
  - `CONNECTOR_STREAM_IDLE_TIMEOUT`: thời gian CLI đợi quote trước khi dừng (mặc định 10).
  - `CONNECTOR_LOG_LEVEL`: log level gốc của toàn hệ thống (DEBUG, INFO, ...; mặc định INFO).
  - `CONNECTOR_WSS_HOST` / `CONNECTOR_WSS_PORT` / `CONNECTOR_WSS_LOG_LEVEL`: cấu hình server WSS.
  - `CONNECTOR_WSS_SUBSCRIBE_TIMEOUT`: thời gian client được phép chờ trước khi gửi payload subscribe (mặc định 10).

## Chạy bằng Poetry

```bash
poetry install
poetry run connector-cli binance BTCUSDT ETHUSDT --market spot --limit 5
```

### WebSocket server

```bash
poetry run connector-wss --host 0.0.0.0 --port 8765
```

Client kết nối tới `ws://<host>:<port>` và gửi JSON subscribe giống thông số gốc:

```json
{
  "exchange": "binance",
  "market": "um",
  "symbols": ["BTCUSDT", "ETHUSDT"],
  "limit": 0
}
```

Server phản hồi `type=quote` với các trường `exchange`, `symbol`, `market`, `price`, `timestamp`.

Các tham số chính:

- `exchange`: `binance`, `okx`, `bybit`, `gateio`, `bitget`.
- `symbols`: danh sách symbol/instId cần subscribe (ví dụ `BTCUSDT`, `BTC-USDT-SWAP`, `BTC_USDT`).
- `--market`: loại thị trường/contract tùy exchange (binance: `spot|um|cm`, bybit: `spot|linear|inverse`, gateio/bitget: `spot|um|cm`, okx: tùy instType máy in `swap`, `futures`, ...).
- `--limit`: số lượng quote in ra trước khi thoát (0 = stream vô hạn).

Ví dụ nhanh:

```bash
# Binance USD-M perpetual
poetry run connector-cli binance BTCUSDT ETHUSDT --market um --limit 20

# OKX perpetual (instId format của OKX)
poetry run connector-cli okx BTC-USDT-SWAP ETH-USDT-SWAP --limit 10

# Bybit linear futures
poetry run connector-cli bybit BTCUSDT ETHUSDT --market linear --limit 10

# Gate.io spot pairs
poetry run connector-cli gateio BTC_USDT ETH_USDT --market spot --limit 10
```

> Sandbox này không có network nên bạn cần chạy ở môi trường của bạn để nhận dữ liệu thật. Hãy chú ý tới giới hạn kết nối, chính sách ping/pong và quota của từng sàn khi stream nhiều symbol.

## Kiểm tra chất lượng

```bash
poetry run ruff check src
poetry run mypy src
poetry run pytest
```

## Test connector hàng loạt:
```bash
poetry run python test/run_all_ws_subscriptions.py --batch-size 100 --limit 60 --concurrency 24
```

## Mở rộng

- Áp dụng backpressure hoặc buffer tùy theo nhu cầu, ví dụ push vào queue nội bộ.
- Bổ sung health-check, metrics và cấu hình backoff linh hoạt cho cơ chế reconnect nếu cần.
- Triển khai test cho `StreamPrices` bằng cách mock repository và test integration cho WebSocket client bằng cách stub server.
- Tách cấu hình (timeout, ping, limit) ra file config hoặc inject qua DI container.

## References:
- OKX: https://www.okx.com/docs-v5/en/#public-data-websocket-index-candlesticks-channel
- GateIO: https://www.gate.com/docs/developers/futures/ws/en/#candlesticks-api
- Bybit: https://bybit-exchange.github.io/docs/v5/websocket/public/kline
- Binance: https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Kline-Candlestick-Streams
- Hyperliquid: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions