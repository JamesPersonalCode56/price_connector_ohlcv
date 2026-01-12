## WS_CONNECT_FAILED

- Tiền đề: Endpoint WS của sàn không reachable (DNS lỗi hoặc TLS handshake fail).
- Bước test:
  1) Cấu hình endpoint sai domain (vd. `wss://invalid-binance.com/ws`).
  2) Gửi payload subscribe hợp lệ qua WS server.
  3) Quan sát kết quả trả về cho client.
- Kỳ vọng:
  - Client nhận `type=error`, `code=WS_CONNECT_FAILED`.
  - `exchange_message` ghi lại nguyên nhân kết nối (DNS/TLS).
  - Log và metrics tăng counter cho lỗi kết nối.
