from __future__ import annotations

from domain.repositories import PriceFeedRepository
from infrastructure.binance.repositories import BinancePriceFeedRepository
from infrastructure.bybit.repositories import BybitPriceFeedRepository
from infrastructure.gateio.repositories import GateioPriceFeedRepository
from infrastructure.hyperliquid.repositories import HyperliquidPriceFeedRepository
from infrastructure.okx.repositories import OkxPriceFeedRepository


def build_price_feed_repository(
    exchange: str, contract_type: str | None
) -> PriceFeedRepository:
    """Factory to construct the correct repository implementation for an exchange."""
    normalized_contract_type = (contract_type or "").lower() if contract_type else None
    if exchange == "binance":
        if not normalized_contract_type:
            raise ValueError("Binance connector requires --market (spot|um|cm)")
        return BinancePriceFeedRepository(normalized_contract_type)
    if exchange == "okx":
        return OkxPriceFeedRepository(normalized_contract_type)
    if exchange == "bybit":
        return BybitPriceFeedRepository(normalized_contract_type or "spot")
    if exchange == "gateio":
        return GateioPriceFeedRepository(normalized_contract_type or "spot")
    if exchange == "hyperliquid":
        return HyperliquidPriceFeedRepository(normalized_contract_type or "usdm")
    raise ValueError(f"Unsupported exchange: {exchange}")
