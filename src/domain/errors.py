from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    WS_CONNECT_FAILED = "WS_CONNECT_FAILED"
    WS_SUBSCRIBE_REJECTED = "WS_SUBSCRIBE_REJECTED"
    WS_STREAM_TIMEOUT = "WS_STREAM_TIMEOUT"
    WS_PROTOCOL_ERROR = "WS_PROTOCOL_ERROR"
    REST_BACKFILL_FAILED = "REST_BACKFILL_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    UNSUPPORTED_CONTRACT_TYPE = "UNSUPPORTED_CONTRACT_TYPE"
    INVALID_SYMBOL = "INVALID_SYMBOL"
    INTERNAL_QUEUE_BACKPRESSURE = "INTERNAL_QUEUE_BACKPRESSURE"
    CONNECTION_POOL_BUSY = "CONNECTION_POOL_BUSY"
    UNKNOWN = "UNKNOWN"


def error_payload(
    code: ErrorCode,
    message: str,
    *,
    exchange: str | None = None,
    contract_type: str | None = None,
    symbols: list[str] | None = None,
    exchange_message: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": "error",
        "code": code.value,
        "message": message,
    }
    if exchange is not None:
        payload["exchange"] = exchange
    if contract_type is not None:
        payload["contract_type"] = contract_type
    if symbols is not None:
        payload["symbols"] = symbols
    if exchange_message:
        payload["exchange_message"] = exchange_message
    return payload
