"""Example client demonstrating how to subscribe to the local WebSocket server for Bybit inverse (coin-m) perpetual."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import websockets


async def stream_quotes() -> None:
    url = "ws://localhost:8765"
    subscription: dict[str, Any] = {
        "exchange": "bybit",
        "contract_type": "inverse",  # aliases: cm, coin-m
        "symbols": ["BTCUSD"],
    }

    async with websockets.connect(url) as websocket:
        await websocket.send(json.dumps(subscription))
        async for message in websocket:
            print(message)


if __name__ == "__main__":
    asyncio.run(stream_quotes())
