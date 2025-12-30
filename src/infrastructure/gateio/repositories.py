from __future__ import annotations

from infrastructure.common import (
    ContractTypeResolver,
    RegistryBackedPriceFeedRepository,
)
from infrastructure.exchange_config import EXCHANGE_WS_ENDPOINTS

from .client import GateioClientConfig, GateioWebSocketClient

_GATEIO_CONFIG = EXCHANGE_WS_ENDPOINTS["gateio"]

_CONFIG_RESOLVER: ContractTypeResolver[GateioClientConfig] = ContractTypeResolver(
    {
        "spot": lambda: GateioClientConfig(
            base_stream_url=_GATEIO_CONFIG["spot"].base_stream_url,
            channel="spot.candlesticks",
            contract_type="spot",
            interval=_GATEIO_CONFIG["spot"].default_interval,
        ),
        "um": lambda: GateioClientConfig(
            base_stream_url=_GATEIO_CONFIG["um"].base_stream_url,
            channel="futures.candlesticks",
            contract_type="um",
            interval=_GATEIO_CONFIG["um"].default_interval,
        ),
        "cm": lambda: GateioClientConfig(
            base_stream_url=_GATEIO_CONFIG["cm"].base_stream_url,
            channel="futures.candlesticks",
            contract_type="cm",
            interval=_GATEIO_CONFIG["cm"].default_interval,
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
