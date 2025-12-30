## WS_STREAM_TIMEOUT

- Tiền đề: Subscribe thành công nhưng không nhận quote trong thời gian timeout.
- Bước test:
  1) Đặt `message_timeout` nhỏ (vd. 5s) trong WS server.
  2) Subscribe symbol thanh khoản thấp hoặc tạm ngừng giao dịch.
  3) Chờ quá timeout.
- Kỳ vọng:
  - Client nhận `type=error`, `code=WS_STREAM_TIMEOUT`.
  - Nếu có backfill, hệ thống thử REST; nếu REST fail thì tiếp tục báo lỗi khác (REST_BACKFILL_FAILED).
  - Log ghi timeout và số symbol bị ảnh hưởng.
