"""Utility script to subscribe to every supported exchange/contract/symbol combination.

The script fetches the available instruments from each exchange's public REST API and
then exercises the local WebSocket server by subscribing in batches. Use ``--dry-run``
to inspect the discovered instruments without opening any WebSocket connections.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Sequence

import httpx
import websockets

DEFAULT_WS_URL = "ws://localhost:8765"
DEFAULT_LIMIT = 1
DEFAULT_BATCH_SIZE = 50
DEFAULT_MESSAGE_TIMEOUT = 30.0

BinanceSymbolMap = Mapping[str, list[str]]
BybitSymbolMap = Mapping[str, list[str]]
GateioSymbolMap = Mapping[str, list[str]]
HyperliquidSymbolMap = Mapping[str, list[str]]
OkxSymbolMap = Mapping[str, list[str]]


@dataclass(slots=True)
class SubscriptionJob:
    exchange: str
    contract_type: str | None
    symbols: list[str]
    batch_index: int
    batch_total: int


class SubscriptionBatchError(RuntimeError):
    def __init__(
        self,
        system_message: str,
        symbols: list[str] | None = None,
        *,
        exchange_message: str | None = None,
    ) -> None:
        self.system_message = system_message
        self.exchange_message = exchange_message
        self.symbols = symbols or []
        message = system_message
        if exchange_message:
            message = f"{system_message} | exchange_message: {exchange_message}"
        super().__init__(message)


def chunked(sequence: Sequence[str], size: int) -> Iterator[list[str]]:
    if size <= 0 or size >= len(sequence):
        yield list(sequence)
        return
    for start in range(0, len(sequence), size):
        yield list(sequence[start : start + size])


def build_error_from_payload(
    payload: Mapping[str, Any], job: SubscriptionJob
) -> SubscriptionBatchError:
    system_message = str(
        payload.get("system_message") or payload.get("message") or "subscription error"
    )
    exchange_message_raw = payload.get("exchange_message")
    exchange_message = str(exchange_message_raw) if exchange_message_raw else None
    exchange = str(payload.get("exchange") or job.exchange)
    contract_type = str(payload.get("contract_type") or job.contract_type or "default")
    raw_symbols = payload.get("symbols")
    if isinstance(raw_symbols, list) and all(
        isinstance(symbol, str) for symbol in raw_symbols
    ):
        symbols = list(raw_symbols)
    else:
        symbols = job.symbols
    details = [
        f"exchange={exchange}",
        f"contract_type={contract_type}",
        f"symbols_count={len(symbols)}",
    ]
    error_message = f"{system_message} ({'; '.join(details)})"
    return SubscriptionBatchError(
        error_message,
        symbols,
        exchange_message=exchange_message,
    )


async def fetch_binance_symbols() -> BinanceSymbolMap:
    endpoints = {
        "spot": "https://api.binance.com/api/v3/exchangeInfo",
        "usdm": "https://fapi.binance.com/fapi/v1/exchangeInfo",
        "coinm": "https://dapi.binance.com/dapi/v1/exchangeInfo",
    }
    results: dict[str, list[str]] = {}
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        for contract_type, url in endpoints.items():
            try:
                response = await client.get(url)
                response.raise_for_status()
            except Exception as exc:  # pragma: no cover - network failure surface
                print(f"[binance::{contract_type}] REST fetch failed: {exc}")
                results[contract_type] = []
                continue

            payload = response.json()
            symbols: list[str] = []
            for entry in payload.get("symbols", []):
                status = (
                    entry.get("status") or entry.get("contractStatus") or ""
                ).upper()
                if status != "TRADING":
                    continue
                symbol = entry.get("symbol")
                if symbol:
                    symbols.append(symbol)
            results[contract_type] = sorted(set(symbols))
    return results


async def fetch_bybit_symbols() -> BybitSymbolMap:
    categories = {
        "spot": "spot",
        "linear": "linear",
        "inverse": "inverse",
    }
    base_url = "https://api.bybit.com/v5/market/instruments-info"
    results: dict[str, list[str]] = {}
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        for contract_type, category in categories.items():
            symbols: list[str] = []
            cursor: str | None = None
            while True:
                params = {"category": category, "limit": 1000}
                if cursor:
                    params["cursor"] = cursor
                try:
                    response = await client.get(base_url, params=params)
                    response.raise_for_status()
                except Exception as exc:  # pragma: no cover - network failure surface
                    print(f"[bybit::{contract_type}] REST fetch failed: {exc}")
                    symbols = []
                    break

                payload = response.json()
                result_block = payload.get("result") or {}
                items = result_block.get("list") or []
                for item in items:
                    status = (item.get("status") or "").lower()
                    if status != "trading":
                        continue
                    symbol = item.get("symbol")
                    if symbol:
                        symbols.append(symbol)
                cursor = result_block.get("nextPageCursor")
                if not cursor:
                    break
            results[contract_type] = sorted(set(symbols))
    return results


async def fetch_gateio_symbols() -> GateioSymbolMap:
    results: dict[str, list[str]] = {}

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        # Spot symbols
        try:
            response = await client.get(
                "https://api.gateio.ws/api/v4/spot/currency_pairs"
            )
            response.raise_for_status()
            spot_symbols = [
                entry["id"]
                for entry in response.json()
                if isinstance(entry, dict) and entry.get("trade_status") == "tradable"
            ]
        except Exception as exc:  # pragma: no cover - network failure surface
            print(f"[gateio::spot] REST fetch failed: {exc}")
            spot_symbols = []
        results["spot"] = sorted(set(spot_symbols))

        # USDT-margined (um) futures contracts
        try:
            response = await client.get(
                "https://api.gateio.ws/api/v4/futures/usdt/contracts"
            )
            response.raise_for_status()
            um_symbols = [
                entry["name"]
                for entry in response.json()
                if isinstance(entry, dict) and entry.get("status") == "trading"
            ]
        except Exception as exc:  # pragma: no cover - network failure surface
            print(f"[gateio::um] REST fetch failed: {exc}")
            um_symbols = []
        results["um"] = sorted(set(um_symbols))

        # Coin-margined (cm) delivery contracts
        try:
            response = await client.get(
                "https://api.gateio.ws/api/v4/futures/contracts"
            )
            response.raise_for_status()
            cm_symbols = [
                entry["name"]
                for entry in response.json()
                if isinstance(entry, dict) and entry.get("status") == "trading"
            ]
        except Exception as exc:  # pragma: no cover - network failure surface
            print(f"[gateio::cm] REST fetch failed: {exc}")
            cm_symbols = []
        results["cm"] = sorted(set(cm_symbols))

    return results


async def fetch_hyperliquid_symbols() -> HyperliquidSymbolMap:
    base_url = "https://api.hyperliquid.xyz/info"
    results: dict[str, list[str]] = {}

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        # Spot universe
        try:
            response = await client.post(base_url, json={"type": "spotMeta"})
            response.raise_for_status()
            payload = response.json()
            spot_entries = payload.get("universe") or []
            spot_symbols = [
                str(entry["name"])
                for entry in spot_entries
                if isinstance(entry, dict)
                and entry.get("name")
                and "/" in str(entry["name"])
                and entry.get("isCanonical", True)
            ]
        except Exception as exc:  # pragma: no cover - network failure surface
            print(f"[hyperliquid::spot] REST fetch failed: {exc}")
            spot_symbols = []
        results["spot"] = sorted(set(spot_symbols))

        # Perpetual universe
        try:
            response = await client.post(base_url, json={"type": "meta"})
            response.raise_for_status()
            payload = response.json()
            meta_entries = payload.get("universe") or []
            coins = [
                str(entry["name"])
                for entry in meta_entries
                if isinstance(entry, dict) and entry.get("name")
            ]
        except Exception as exc:  # pragma: no cover - network failure surface
            print(f"[hyperliquid::perp] REST fetch failed: {exc}")
            coins = []

    unique_coins = sorted(set(coins))
    results["usdm"] = [f"{coin}-USDC-SWAP" for coin in unique_coins]
    results["coinm"] = [f"{coin}-USD-SWAP" for coin in unique_coins]

    return results


async def fetch_okx_symbols() -> OkxSymbolMap:
    base_url = "https://www.okx.com/api/v5/public/instruments"
    results: dict[str, list[str]] = {}

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        try:
            response = await client.get(base_url, params={"instType": "SPOT"})
            response.raise_for_status()
            spot_symbols = [
                entry["instId"]
                for entry in response.json().get("data", [])
                if isinstance(entry, dict) and entry.get("state") == "live"
            ]
        except Exception as exc:  # pragma: no cover - network failure surface
            print(f"[okx::spot] REST fetch failed: {exc}")
            spot_symbols = []
        results["spot"] = sorted(set(spot_symbols))

        try:
            response = await client.get(base_url, params={"instType": "SWAP"})
            response.raise_for_status()
            swap_entries = [
                entry
                for entry in response.json().get("data", [])
                if isinstance(entry, dict) and entry.get("state") == "live"
            ]
        except Exception as exc:  # pragma: no cover - network failure surface
            print(f"[okx::swap] REST fetch failed: {exc}")
            swap_entries = []

    swap_usd = [
        entry["instId"]
        for entry in swap_entries
        if entry.get("settleCcy") in {"USDT", "USDC", "USD"}
    ]
    swap_coin = [
        entry["instId"]
        for entry in swap_entries
        if entry.get("settleCcy") not in {"USDT", "USDC", "USD"}
    ]
    results["swap"] = sorted(set(swap_usd))
    results["swap_coinm"] = sorted(set(swap_coin))

    return results


async def fetch_symbol_map(
    selected: set[str] | None,
) -> dict[tuple[str, str | None], list[str]]:
    symbol_map: dict[tuple[str, str | None], list[str]] = {}

    if selected is None or "binance" in selected:
        for contract, symbols in (await fetch_binance_symbols()).items():
            symbol_map[("binance", contract)] = symbols

    if selected is None or "bybit" in selected:
        for contract, symbols in (await fetch_bybit_symbols()).items():
            symbol_map[("bybit", contract)] = symbols

    if selected is None or "gateio" in selected:
        for contract, symbols in (await fetch_gateio_symbols()).items():
            symbol_map[("gateio", contract)] = symbols

    if selected is None or "hyperliquid" in selected:
        for contract, symbols in (await fetch_hyperliquid_symbols()).items():
            symbol_map[("hyperliquid", contract)] = symbols

    if selected is None or "okx" in selected:
        for contract, symbols in (await fetch_okx_symbols()).items():
            symbol_map[("okx", contract)] = symbols

    return symbol_map


async def run_subscription(
    job: SubscriptionJob,
    ws_url: str,
    limit: int,
    message_timeout: float,
) -> tuple[SubscriptionJob, int, SubscriptionBatchError | None]:
    payload = {
        "exchange": job.exchange,
        "symbols": job.symbols,
        "limit": limit,
    }
    if job.contract_type:
        payload["contract_type"] = job.contract_type

    try:
        async with websockets.connect(ws_url) as websocket:
            await websocket.send(json.dumps(payload))

            ack_raw = await asyncio.wait_for(websocket.recv(), timeout=message_timeout)
            ack = json.loads(ack_raw)
            if ack.get("type") == "error":
                raise build_error_from_payload(ack, job)

            received = 0
            timeout_hit = False
            while limit <= 0 or received < limit:
                try:
                    raw = await asyncio.wait_for(
                        websocket.recv(), timeout=message_timeout
                    )
                except asyncio.TimeoutError:
                    print(
                        f"[{job.exchange}::{job.contract_type or 'default'}] "
                        f"Timed out waiting for quotes (batch {job.batch_index}/{job.batch_total})"
                    )
                    timeout_hit = True
                    break

                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if message.get("type") == "error":
                    raise build_error_from_payload(message, job)
                quote_symbol = None
                quote_close = None
                quote_timestamp = None
                if message.get("type") == "quote":
                    quote_symbol = message.get("symbol")
                    quote_close = message.get("close")
                    quote_timestamp = message.get("timestamp")
                elif message.get("e") == "kline":
                    kline = message.get("k") or {}
                    quote_symbol = message.get("s") or kline.get("s")
                    quote_close = kline.get("c")
                    quote_timestamp = kline.get("T") or kline.get("t")
                else:
                    continue

                received += 1
                if received == 1:
                    print(
                        f"[{job.exchange}::{job.contract_type or 'default'}] "
                        f"Batch {job.batch_index}/{job.batch_total}: first quote "
                        f"{quote_symbol} close={quote_close} "
                        f"@ {quote_timestamp}"
                    )
            if timeout_hit and received == 0:
                return (
                    job,
                    received,
                    SubscriptionBatchError(
                        "No quotes received before timeout", job.symbols
                    ),
                )
            return job, received, None
    except SubscriptionBatchError as exc:
        print(
            f"[{job.exchange}::{job.contract_type or 'default'}] "
            f"Batch {job.batch_index}/{job.batch_total} failed: {exc}"
        )
        return job, 0, exc
    except Exception as exc:
        print(
            f"[{job.exchange}::{job.contract_type or 'default'}] "
            f"Batch {job.batch_index}/{job.batch_total} failed: {exc}"
        )
        return job, 0, SubscriptionBatchError(str(exc), job.symbols)


async def execute(args: argparse.Namespace) -> None:
    selected = {item.lower() for item in args.exchanges} if args.exchanges else None
    symbol_map = await fetch_symbol_map(selected)

    non_empty = {key: symbols for key, symbols in symbol_map.items() if symbols}
    empty = sorted(set(symbol_map) - set(non_empty))

    print("Discovered instrument universe:")
    for (exchange, contract_type), symbols in sorted(non_empty.items()):
        print(f"  - {exchange}::{contract_type or 'default'} -> {len(symbols)} symbols")
    for exchange, contract_type in empty:
        print(f"  - {exchange}::{contract_type or 'default'} -> 0 symbols (skipped)")

    if args.dry_run:
        return

    batch_size = args.batch_size if args.batch_size and args.batch_size > 0 else 0
    jobs: list[SubscriptionJob] = []

    for (exchange, contract_type), symbols in sorted(non_empty.items()):
        batches = list(chunked(symbols, batch_size)) if batch_size else [list(symbols)]
        total = len(batches)
        for index, batch in enumerate(batches, start=1):
            jobs.append(
                SubscriptionJob(
                    exchange=exchange,
                    contract_type=contract_type,
                    symbols=batch,
                    batch_index=index,
                    batch_total=total,
                )
            )

    print(f"Executing {len(jobs)} subscription batches against {args.ws_url}")

    semaphore = asyncio.Semaphore(args.concurrency) if args.concurrency > 0 else None

    async def _run_with_limit(
        job: SubscriptionJob,
    ) -> tuple[SubscriptionJob, int, SubscriptionBatchError | None]:
        if semaphore is None:
            return await run_subscription(
                job, args.ws_url, args.limit, args.message_timeout
            )
        async with semaphore:
            return await run_subscription(
                job, args.ws_url, args.limit, args.message_timeout
            )

    results = await asyncio.gather(*(_run_with_limit(job) for job in jobs))

    failures: list[tuple[SubscriptionJob, SubscriptionBatchError]] = []
    for job, received, error in results:
        if error is not None:
            failures.append((job, error))
        elif args.limit > 0 and received == 0:
            failures.append(
                (job, SubscriptionBatchError("No quotes received", job.symbols))
            )

    if failures:
        print("\nBatches that did not stream successfully:")
        failed_symbol_total = 0
        for job, error in failures:
            print(
                f"  - {job.exchange}::{job.contract_type or 'default'} batch "
                f"{job.batch_index}/{job.batch_total} ({len(job.symbols)} symbols): {error}"
            )
            symbols = error.symbols or job.symbols
            failed_symbol_total += len(symbols)
            for symbol in symbols:
                print(f"      * {symbol}")
        print(f"\nTotal symbols without quotes: {failed_symbol_total}")
    else:
        print("\nAll batches streamed successfully.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Subscribe to all available exchange/contract/symbol combinations via the local WS server."
    )
    parser.add_argument(
        "--ws-url",
        default=DEFAULT_WS_URL,
        help=f"WebSocket server URL (default: {DEFAULT_WS_URL})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Number of quote messages to collect per subscription batch (0 = unlimited).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Number of symbols per subscription batch (0 = send all symbols at once).",
    )
    parser.add_argument(
        "--message-timeout",
        type=float,
        default=DEFAULT_MESSAGE_TIMEOUT,
        help="Seconds to wait for the next WebSocket message before aborting the batch.",
    )
    parser.add_argument(
        "--exchanges",
        nargs="+",
        help="Optional list of exchanges to include (default: all).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only fetch and display the instrument lists without opening WebSocket connections.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Maximum number of concurrent subscription batches (0 = no limit).",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(execute(args))


if __name__ == "__main__":
    main()
