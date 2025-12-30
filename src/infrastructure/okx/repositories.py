from __future__ import annotations

from infrastructure.common import WebSocketPriceFeedRepository
from infrastructure.exchange_config import EXCHANGE_WS_ENDPOINTS

from .client import OkxClientConfig, OkxWebSocketClient


class OkxPriceFeedRepository(WebSocketPriceFeedRepository[OkxClientConfig]):
    client_cls = OkxWebSocketClient

    def __init__(self, contract_type: str | None = None) -> None:
        super().__init__(contract_type)

    def _build_config(self, contract_type: str | None) -> OkxClientConfig:
        normalized = (contract_type or "").lower()
        if normalized in {"swap", "swap_coinm"}:
            inst_type = "SWAP"
        elif normalized == "spot":
            inst_type = "SPOT"
        else:
            inst_type = None

        config_map = EXCHANGE_WS_ENDPOINTS.get("okx", {})
        if normalized and normalized in config_map:
            ws_config = config_map[normalized]
        else:
            ws_config = config_map.get("spot")

        base_stream_url = (
            ws_config.base_stream_url if ws_config else "wss://ws.okx.com:8443/ws/v5/business"
        )
        interval = ws_config.default_interval if ws_config else "1m"
        return OkxClientConfig(
            base_stream_url=base_stream_url,
            default_inst_type=inst_type,
            interval=interval,
        )
