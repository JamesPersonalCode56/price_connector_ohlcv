## REST_BACKFILL_FAILED

- Tiền đề: Sau khi timeout WS, hệ thống gọi REST backfill nhưng fail.
- Bước test:
  1) Mock REST endpoint trả 500 hoặc timeout.
  2) Trước đó đã kích hoạt nhánh backfill (không có quote WS).
  3) Chờ kết quả trả về client.
- Kỳ vọng:
  - Client nhận `type=error`, `code=REST_BACKFILL_FAILED`, `exchange_message` nêu lỗi HTTP.
  - Không có quote được gửi ra.
  - Metrics lỗi REST tăng.
