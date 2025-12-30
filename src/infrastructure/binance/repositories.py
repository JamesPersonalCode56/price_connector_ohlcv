from __future__ import annotations

from infrastructure.common import (
    ContractTypeResolver,
    RegistryBackedPriceFeedRepository,
)
from infrastructure.exchange_config import EXCHANGE_WS_ENDPOINTS

from .client import BinanceWebSocketClient, BinanceWsConfig

_BINANCE_CONFIG = EXCHANGE_WS_ENDPOINTS["binance"]

_CONFIG_RESOLVER: ContractTypeResolver[BinanceWsConfig] = ContractTypeResolver(
    {
        "spot": lambda: BinanceWsConfig(
            contract_type="spot",
            base_stream_url=_BINANCE_CONFIG["spot"].base_stream_url,
            interval=_BINANCE_CONFIG["spot"].default_interval,
        ),
        "usdm": lambda: BinanceWsConfig(
            contract_type="usdm",
            base_stream_url=_BINANCE_CONFIG["usdm"].base_stream_url,
            interval=_BINANCE_CONFIG["usdm"].default_interval,
        ),
        "coinm": lambda: BinanceWsConfig(
            contract_type="coinm",
            base_stream_url=_BINANCE_CONFIG["coinm"].base_stream_url,
            interval=_BINANCE_CONFIG["coinm"].default_interval,
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
