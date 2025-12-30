## UNSUPPORTED_CONTRACT_TYPE

- Tiền đề: Client gửi contract_type không hợp lệ cho sàn.
- Bước test:
  1) Payload với `exchange="binance"`, `contract_type="swap"` (không được hỗ trợ).
  2) Gửi qua WS server.
- Kỳ vọng:
  - Server validate và trả ngay `type=error`, `code=UNSUPPORTED_CONTRACT_TYPE`.
  - Không cố kết nối WS ra sàn.
  - Log nêu rõ contract_type hợp lệ (spot|usdm|coinm).
