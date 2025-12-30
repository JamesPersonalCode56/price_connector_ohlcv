from __future__ import annotations

from infrastructure.common import (
    ContractTypeResolver,
    RegistryBackedPriceFeedRepository,
)
from infrastructure.exchange_config import EXCHANGE_WS_ENDPOINTS

from .client import HyperliquidWebSocketClient, HyperliquidWsConfig

_HYPER_CONFIG = EXCHANGE_WS_ENDPOINTS["hyperliquid"]

_CONFIG_RESOLVER: ContractTypeResolver[HyperliquidWsConfig] = ContractTypeResolver(
    {
        "spot": lambda: HyperliquidWsConfig(
            market_type="spot",
            contract_type="spot",
            base_ws_url=_HYPER_CONFIG["spot"].base_stream_url,
            interval=_HYPER_CONFIG["spot"].default_interval,
        ),
        "usdm": lambda: HyperliquidWsConfig(
            market_type="perp",
            contract_type="usdm",
            base_ws_url=_HYPER_CONFIG["usdm"].base_stream_url,
            interval=_HYPER_CONFIG["usdm"].default_interval,
        ),
        "coinm": lambda: HyperliquidWsConfig(
            market_type="perp",
            contract_type="coinm",
            base_ws_url=_HYPER_CONFIG["coinm"].base_stream_url,
            interval=_HYPER_CONFIG["coinm"].default_interval,
        ),
    },
    aliases={
        "usd-m": "usdm",
        "perp": "usdm",
        "swap": "usdm",
        "cm": "coinm",
    },
    default_key="usdm",
    error_message="Unsupported Hyperliquid contract_type. Use spot, usdm (perp), or coinm.",
)


class HyperliquidPriceFeedRepository(
    RegistryBackedPriceFeedRepository[HyperliquidWsConfig]
):
    client_cls = HyperliquidWebSocketClient
    resolver = _CONFIG_RESOLVER

    def __init__(self, contract_type: str | None = None) -> None:
        super().__init__(contract_type)
