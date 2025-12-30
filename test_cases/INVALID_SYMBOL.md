## INVALID_SYMBOL

- Tiền đề: Symbol không hợp lệ hoặc sai format cho sàn/contract_type.
- Bước test:
  1) Dùng symbol không thuộc danh sách REST discovery (vd. Binance spot: `["FOOXYZ"]`).
  2) Gửi subscribe và chờ ack/error.
- Kỳ vọng:
  - Nhận `type=error`, `code=INVALID_SYMBOL`, kèm danh sách symbol bị từ chối.
  - Không gửi quote; connection vẫn có thể phục vụ symbol hợp lệ khác.
  - Log ghi rõ symbol và contract_type.
