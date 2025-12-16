from __future__ import annotations

from infrastructure.common import (
    ContractTypeResolver,
    RegistryBackedPriceFeedRepository,
)

from .client import BinanceWebSocketClient, BinanceWsConfig

_CONFIG_RESOLVER: ContractTypeResolver[BinanceWsConfig] = ContractTypeResolver(
    {
        "spot": lambda: BinanceWsConfig(
            contract_type="spot",
            base_stream_url="wss://stream.binance.com:9443",
        ),
        "usdm": lambda: BinanceWsConfig(
            contract_type="usdm",
            base_stream_url="wss://fstream.binance.com",
        ),
        "coinm": lambda: BinanceWsConfig(
            contract_type="coinm",
            base_stream_url="wss://dstream.binance.com",
        ),
    },
    aliases={
        "um": "usdm",
        "cm": "coinm",
    },
    error_message="Unsupported Binance contract_type: {value}",
    missing_message="Binance connector requires a contract type",
)


class BinancePriceFeedRepository(RegistryBackedPriceFeedRepository[BinanceWsConfig]):
    client_cls = BinanceWebSocketClient
    resolver = _CONFIG_RESOLVER

    def __init__(self, contract_type: str) -> None:
        super().__init__(contract_type)
