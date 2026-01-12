## WS_SUBSCRIBE_REJECTED

- Tiền đề: Kết nối WS thành công nhưng sàn trả error khi subscribe.
- Bước test:
  1) Dùng endpoint đúng, gửi payload với `symbols` chứa symbol sai format (vd. Binance spot: `["BTC-USDT"]` thay vì `["BTCUSDT"]`).
  2) Nhận ack/error đầu tiên từ sàn qua server.
  3) Ghi nhận payload error.
- Kỳ vọng:
  - Client nhận `type=error`, `code=WS_SUBSCRIBE_REJECTED`, kèm `symbols` liên quan.
  - `exchange_message` chứa chi tiết error của sàn.
  - Không có quote nào được forward, connection có thể bị đóng hoặc vẫn mở tùy sàn.
