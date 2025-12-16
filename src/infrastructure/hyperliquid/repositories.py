from __future__ import annotations

from infrastructure.common import (
    ContractTypeResolver,
    RegistryBackedPriceFeedRepository,
)

from .client import HyperliquidWebSocketClient, HyperliquidWsConfig

_CONFIG_RESOLVER: ContractTypeResolver[HyperliquidWsConfig] = ContractTypeResolver(
    {
        "spot": lambda: HyperliquidWsConfig(market_type="spot", contract_type="spot"),
        "usdm": lambda: HyperliquidWsConfig(market_type="perp", contract_type="usdm"),
        "coinm": lambda: HyperliquidWsConfig(market_type="perp", contract_type="coinm"),
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
