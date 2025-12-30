## RATE_LIMITED

- Tiền đề: Sàn trả thông báo rate limit hoặc ngắt kết nối khi vượt giới hạn subscribe/req.
- Bước test:
  1) Gửi liên tiếp nhiều request subscribe (vd. batch nhỏ nhưng nhiều lần trong 1s) vượt hạn mức sàn.
  2) Quan sát phản hồi hoặc disconnect từ sàn.
- Kỳ vọng:
  - Client nhận `type=error`, `code=RATE_LIMITED`, kèm `exchange_message` nếu sàn cung cấp.
  - Hệ thống áp dụng backoff/retry có kiểm soát (không flood tiếp).
  - Log/metrics ghi nhận rate limit.
