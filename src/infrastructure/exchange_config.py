from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ExchangeWsConfig:
    base_stream_url: str
    default_contract_type: str
    max_symbols_per_connection: int
    message_timeout: float
    default_interval: str = "1m"


# Static WS endpoint map per exchange/contract_type
EXCHANGE_WS_ENDPOINTS: Mapping[str, Mapping[str, ExchangeWsConfig]] = {
    "binance": {
        "spot": ExchangeWsConfig(
            base_stream_url="wss://stream.binance.com:9443/ws",
            default_contract_type="spot",
            max_symbols_per_connection=200,
            message_timeout=15.0,
        ),
        "usdm": ExchangeWsConfig(
            base_stream_url="wss://fstream.binance.com/ws",
            default_contract_type="usdm",
            max_symbols_per_connection=200,
            message_timeout=15.0,
        ),
        "coinm": ExchangeWsConfig(
            base_stream_url="wss://dstream.binance.com/ws",
            default_contract_type="coinm",
            max_symbols_per_connection=200,
            message_timeout=15.0,
        ),
    },
    "okx": {
        "spot": ExchangeWsConfig(
            base_stream_url="wss://ws.okx.com:8443/ws/v5/business",
            default_contract_type="spot",
            max_symbols_per_connection=200,
            message_timeout=15.0,
        ),
        "swap": ExchangeWsConfig(
            base_stream_url="wss://ws.okx.com:8443/ws/v5/business",
            default_contract_type="swap",
            max_symbols_per_connection=200,
            message_timeout=15.0,
        ),
        "swap_coinm": ExchangeWsConfig(
            base_stream_url="wss://ws.okx.com:8443/ws/v5/business",
            default_contract_type="swap_coinm",
            max_symbols_per_connection=200,
            message_timeout=15.0,
        ),
    },
    "bybit": {
        "spot": ExchangeWsConfig(
            base_stream_url="wss://stream.bybit.com/v5/public/spot",
            default_contract_type="spot",
            max_symbols_per_connection=200,
            message_timeout=15.0,
        ),
        "linear": ExchangeWsConfig(
            base_stream_url="wss://stream.bybit.com/v5/public/linear",
            default_contract_type="linear",
            max_symbols_per_connection=200,
            message_timeout=15.0,
        ),
        "inverse": ExchangeWsConfig(
            base_stream_url="wss://stream.bybit.com/v5/public/inverse",
            default_contract_type="inverse",
            max_symbols_per_connection=200,
            message_timeout=15.0,
        ),
    },
    "gateio": {
        "spot": ExchangeWsConfig(
            base_stream_url="wss://api.gateio.ws/ws/v4/",
            default_contract_type="spot",
            max_symbols_per_connection=100,
            message_timeout=15.0,
        ),
        "um": ExchangeWsConfig(
            base_stream_url="wss://fx-ws.gateio.ws/v4/ws/usdt",
            default_contract_type="um",
            max_symbols_per_connection=100,
            message_timeout=15.0,
        ),
        "cm": ExchangeWsConfig(
            base_stream_url="wss://fx-ws.gateio.ws/v4/ws/{settle}",
            default_contract_type="cm",
            max_symbols_per_connection=50,
            message_timeout=15.0,
        ),
    },
    "hyperliquid": {
        "spot": ExchangeWsConfig(
            base_stream_url="wss://api.hyperliquid.xyz/ws",
            default_contract_type="spot",
            max_symbols_per_connection=200,
            message_timeout=15.0,
        ),
        "usdm": ExchangeWsConfig(
            base_stream_url="wss://api.hyperliquid.xyz/ws",
            default_contract_type="usdm",
            max_symbols_per_connection=200,
            message_timeout=15.0,
        ),
        "coinm": ExchangeWsConfig(
            base_stream_url="wss://api.hyperliquid.xyz/ws",
            default_contract_type="coinm",
            max_symbols_per_connection=200,
            message_timeout=15.0,
        ),
    },
}
