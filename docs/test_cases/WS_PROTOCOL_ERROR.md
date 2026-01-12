## WS_PROTOCOL_ERROR

- Tiền đề: Payload từ sàn sai định dạng (không parse được hoặc thiếu trường bắt buộc).
- Bước test:
  1) Mock client sàn trả message JSON thiếu field giá hoặc timestamp.
  2) Hệ thống cố parse và fail.
  3) Quan sát phản hồi tới client.
- Kỳ vọng:
  - Client nhận `type=error`, `code=WS_PROTOCOL_ERROR`.
  - Connection có thể vẫn giữ, nhưng symbol batch đó bị đánh dấu lỗi.
  - Log chi tiết message gốc (ẩn PII nếu có).
