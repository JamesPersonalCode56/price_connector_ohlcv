## UNKNOWN

- Tiền đề: Lỗi không phân loại được vào nhóm đã định nghĩa.
- Bước test:
  1) Mock exception bất ngờ (vd. lỗi runtime trong parser chưa được catch riêng).
  2) Thực thi luồng subscribe/stream để kích hoạt exception đó.
  3) Theo dõi phản hồi.
- Kỳ vọng:
  - Client nhận `type=error`, `code=UNKNOWN`, `message` mô tả ngắn gọn.
  - Log chứa stacktrace đầy đủ để debug.
  - Không làm rơi connection khác; hệ thống tiếp tục phục vụ các symbol không bị ảnh hưởng.
