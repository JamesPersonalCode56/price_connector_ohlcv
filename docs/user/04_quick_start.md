# Chapter 4 - Quick Start

1) Start the WebSocket server:
   poetry run connector-wss --host 0.0.0.0 --port 8765

2) Connect a client:
   - Send a JSON subscription payload.
   - Example payload:
     {
       "exchange": "binance",
       "contract_type": "spot",
       "symbols": ["BTCUSDT", "ETHUSDT"],
       "limit": 0
     }

3) Receive streaming kline events.
