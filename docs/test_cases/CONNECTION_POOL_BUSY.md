## CONNECTION_POOL_BUSY

- Tiền đề: Cơ chế share kết nối (pool) hết slot, không cấp thêm subscription mới.
- Bước test:
  1) Cấu hình `MAX_CONN_PER_EXCHANGE=1`, `MAX_SYMBOL_PER_CONN` nhỏ (vd. 10).
  2) Gửi nhiều yêu cầu subscribe mới vượt quá capacity pool.
  3) Quan sát phản hồi.
- Kỳ vọng:
  - Nhận `type=error`, `code=CONNECTION_POOL_BUSY`.
  - Không mở kết nối mới ra sàn.
  - Log nêu rõ giới hạn và số symbol/request bị từ chối.
