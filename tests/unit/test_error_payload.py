from domain.errors import ErrorCode, error_payload


def test_error_payload_structure():
    payload = error_payload(
        ErrorCode.WS_SUBSCRIBE_REJECTED,
        "bad symbol",
        exchange="binance",
        contract_type="spot",
        symbols=["BTCUSDT"],
        exchange_message="invalid symbol",
    )
    assert payload["type"] == "error"
    assert payload["code"] == ErrorCode.WS_SUBSCRIBE_REJECTED.value
    assert payload["message"] == "bad symbol"
    assert payload["exchange"] == "binance"
    assert payload["contract_type"] == "spot"
    assert payload["symbols"] == ["BTCUSDT"]
    assert payload["exchange_message"] == "invalid symbol"
