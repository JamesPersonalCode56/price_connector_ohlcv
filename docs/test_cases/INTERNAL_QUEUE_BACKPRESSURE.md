## INTERNAL_QUEUE_BACKPRESSURE

- Tiền đề: Hàng đợi nội bộ (dual queue/dedup) đầy, không tiêu thụ kịp.
- Bước test:
  1) Mock consumer chậm (sleep) hoặc ngắt tiêu thụ để queue đầy.
  2) Đẩy nhiều quote vào để vượt ngưỡng queue.
  3) Theo dõi phản hồi server.
- Kỳ vọng:
  - Client nhận `type=error`, `code=INTERNAL_QUEUE_BACKPRESSURE`.
  - Hệ thống áp dụng drop/buffer theo cấu hình, log cảnh báo.
  - Metrics queue depth/overflow tăng.
