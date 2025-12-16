from __future__ import annotations

from infrastructure.common import (
    ContractTypeResolver,
    RegistryBackedPriceFeedRepository,
)

from .client import GateioClientConfig, GateioWebSocketClient

_CONFIG_RESOLVER: ContractTypeResolver[GateioClientConfig] = ContractTypeResolver(
    {
        "spot": lambda: GateioClientConfig(
            base_stream_url="wss://api.gateio.ws/ws/v4/",
            channel="spot.candlesticks",
            contract_type="spot",
        ),
        "um": lambda: GateioClientConfig(
            base_stream_url="wss://fx-ws.gateio.ws/v4/ws/usdt",
            channel="futures.candlesticks",
            contract_type="um",
        ),
        "cm": lambda: GateioClientConfig(
            base_stream_url="wss://fx-ws.gateio.ws/v4/ws/{settle}",
            channel="futures.candlesticks",
            contract_type="cm",
        ),
    },
    aliases={
        "usd-m": "um",
        "coin-m": "cm",
    },
    default_key="spot",
    error_message="Unsupported Gate.io contract_type. Use spot, um/usd-m, or cm/coin-m.",
)


class GateioPriceFeedRepository(RegistryBackedPriceFeedRepository[GateioClientConfig]):
    client_cls = GateioWebSocketClient
    resolver = _CONFIG_RESOLVER

    def __init__(self, contract_type: str | None) -> None:
        super().__init__(contract_type)
