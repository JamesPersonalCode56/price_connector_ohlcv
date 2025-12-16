from __future__ import annotations

from infrastructure.common import (
    ContractTypeResolver,
    RegistryBackedPriceFeedRepository,
)

from .client import BybitClientConfig, BybitWebSocketClient

_CONFIG_RESOLVER: ContractTypeResolver[BybitClientConfig] = ContractTypeResolver(
    {
        "spot": lambda: BybitClientConfig(
            base_stream_url="wss://stream.bybit.com/v5/public/spot",
            contract_type="spot",
        ),
        "linear": lambda: BybitClientConfig(
            base_stream_url="wss://stream.bybit.com/v5/public/linear",
            contract_type="linear",
        ),
        "inverse": lambda: BybitClientConfig(
            base_stream_url="wss://stream.bybit.com/v5/public/inverse",
            contract_type="inverse",
        ),
    },
    aliases={
        "um": "linear",
        "usd-m": "linear",
        "perp": "linear",
        "cm": "inverse",
        "coin-m": "inverse",
    },
    default_key="spot",
    error_message="Unsupported Bybit contract_type. Use one of spot, linear (aka um/usd-m), inverse (aka cm/coin-m).",
)


class BybitPriceFeedRepository(RegistryBackedPriceFeedRepository[BybitClientConfig]):
    client_cls = BybitWebSocketClient
    resolver = _CONFIG_RESOLVER

    def __init__(self, contract_type: str | None) -> None:
        super().__init__(contract_type)
