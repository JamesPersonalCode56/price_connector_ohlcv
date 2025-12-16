from __future__ import annotations

import argparse
import asyncio
from datetime import timezone
from typing import Iterable

from application.use_cases.stream_prices import StreamPrices
from config import SETTINGS
from interfaces.repository_factory import build_price_feed_repository

EXCHANGES = {"binance": "Binance", "okx": "OKX", "bybit": "Bybit", "gateio": "Gate.io"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stream crypto prices via WebSocket using clean architecture layers"
    )
    parser.add_argument(
        "exchange", choices=sorted(EXCHANGES.keys()), help="Exchange connector to use"
    )
    parser.add_argument(
        "symbols",
        nargs="+",
        help="Symbols or instrument identifiers to subscribe to",
    )
    parser.add_argument(
        "--market",
        default=None,
        help="Market/contract type (required for some exchanges, e.g. binance: spot|um|cm)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of quotes to print before exiting (0 = run forever)",
    )
    return parser.parse_args()


async def run_stream(
    exchange: str, market: str | None, symbols: Iterable[str], limit: int
) -> None:
    repository = build_price_feed_repository(exchange, market)
    use_case = StreamPrices(repository)

    stream = use_case.execute(symbols)
    counter = 0

    try:
        while True:
            try:
                quote = await asyncio.wait_for(
                    stream.__anext__(), timeout=SETTINGS.connector.stream_idle_timeout
                )
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError:
                print(
                    f"No quotes received in {SETTINGS.connector.stream_idle_timeout:.0f} seconds. Cancelling stream."
                )
                break

            timestamp = quote.timestamp.astimezone(timezone.utc).isoformat()
            print(
                f"[{quote.exchange}::{quote.contract_type}] {quote.symbol} "
                f"O:{quote.open} H:{quote.high} L:{quote.low} C:{quote.close} "
                f"V:{quote.volume} closed={quote.is_closed_candle} @ {timestamp}"
            )

            if limit > 0:
                counter += 1
                if counter >= limit:
                    break
    finally:
        aclose = getattr(stream, "aclose", None)
        if callable(aclose):
            await aclose()


def main() -> None:
    args = parse_args()
    asyncio.run(run_stream(args.exchange, args.market, args.symbols, args.limit))


if __name__ == "__main__":
    main()
