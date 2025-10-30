# Market Data Sources & Domain Mapping

The only domain entity exposed by the connector layer is:

```python
@dataclass(frozen=True)
class PriceQuote:
    exchange: str
    symbol: str
    contract_type: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_num: int
    is_closed_candle: bool
```

Each exchange connector normalises raw WebSocket and REST payloads into the structure above.
The following sections describe the transport endpoints, subscription payloads, response
shapes, and the field mapping per exchange/contract type.

---

## Hyperliquid

### Perpetual (`usdm`, `coinm`)

- **WebSocket endpoint**: `wss://api.hyperliquid.xyz/ws`
- **Subscription payload** (one message per subscription group):

  ```json
  {
    "method": "subscribe",
    "subscription": {
      "type": "candle",
      "coin": "<BASE>",        // e.g. "BTC" or "kPEPE"
      "interval": "1m"
    }
  }
  ```

- **Stream response**:

  ```json
  {
    "channel": "candle",
    "data": {
      "t": 1760670960000,
      "T": 1760671019999,
      "s": "BTC",
      "i": "1m",
      "o": "108900.0",
      "h": "109050.0",
      "l": "108850.0",
      "c": "109000.0",
      "v": "12.34",
      "n": 82
    }
  }
  ```

- **Mapping → `PriceQuote`**:

  | PriceQuote field   | Source                                                    |
  |--------------------|-----------------------------------------------------------|
  | `exchange`         | Literal `"hyperliquid"`                                   |
  | `symbol`           | Original subscription symbol (e.g. `BTC-USDC-SWAP`)       |
  | `contract_type`    | Repository contract selector (`usdm` or `coinm`)          |
  | `timestamp`        | `datetime.utcfromtimestamp(data["t"] / 1000)`             |
  | `open`             | `float(data["o"])`                                        |
  | `high`             | `float(data["h"])`                                        |
  | `low`              | `float(data["l"])`                                        |
  | `close`            | `float(data["c"])`                                        |
  | `volume`           | `float(data["v"])`                                        |
  | `trade_num`        | `int(data["n"])`                                          |
  | `is_closed_candle` | `now_ms >= data["T"]` (if `T` provided)                   |

- **REST backfill**: `POST https://api.hyperliquid.xyz/info`

  - **Request body**:

    ```json
    {
      "type": "candleSnapshot",
      "req": {
        "coin": "<BASE>",
        "interval": "1m",
        "startTime": <epoch-ms> ,
        "endTime": <epoch-ms>
      }
    }
    ```

    `startTime` is computed ~5 intervals before `endTime` to guarantee a candle is
    returned even when the stream is idle.

  - **Response**: array of candle dictionaries matching the WebSocket schema (`t`, `T`,
    `o`, `h`, `l`, `c`, `v`, `n`). The last element is converted with the same mapping
    table above.

### Spot (`spot`)

- **WebSocket**: identical endpoint. `subscription.coin` must include the quote
  (e.g. `"PURR/USDC"`).
- **Mapping**: same as perpetual, but `contract_type` is set to `"spot"` and the
  original symbol keeps the slash form (`PURR/USDC`).
- **REST backfill**: identical `candleSnapshot` request, using the slash symbol in
  `req.coin`.

---

## Binance

### Spot (`spot`)

- **WebSocket endpoint**:
  `wss://stream.binance.com:9443/stream?streams=<symbol>@kline_<interval>` where the
  connector joins all requested symbols into a combined stream.
- **Subscription**: no client-side payload is sent; the stream selection is encoded in
  the URL.
- **Stream response**:

  ```json
  {
    "stream": "btcusdt@kline_1m",
    "data": {
      "E": 1700000000000,
      "k": {
        "t": 1700000000000,
        "T": 1700000059999,
        "s": "BTCUSDT",
        "i": "1m",
        "o": "44100.00",
        "c": "44123.45",
        "h": "44150.00",
        "l": "44080.00",
        "v": "123.456",
        "n": 102,
        "x": false
      }
    }
  }
  ```

- **Mapping**:

  | PriceQuote field   | Source                                              |
  |--------------------|-----------------------------------------------------|
  | `exchange`         | `"binance"`                                         |
  | `symbol`           | `k["s"]`                                            |
  | `contract_type`    | `"spot"`                                            |
  | `timestamp`        | `datetime.utcfromtimestamp((data["E"] or k["T"]) / 1000)` |
  | `open`             | `float(k["o"])`                                     |
  | `high`             | `float(k["h"])`                                     |
  | `low`              | `float(k["l"])`                                     |
  | `close`            | `float(k["c"])`                                     |
  | `volume`           | `float(k["v"])`                                     |
  | `trade_num`        | `int(k["n"])`                                       |
  | `is_closed_candle` | `bool(k["x"])`                                      |

- **REST backfill**: `GET https://api.binance.com/api/v3/klines`

  - **Parameters**: `symbol=<SYMBOL>`, `interval=<INTERVAL>`, `limit=1`
  - **Response**: `[[openTime, open, high, low, close, volume, closeTime, ...]]`
  - **Mapping**: uses the first row; `timestamp` resolves to
    `datetime.utcfromtimestamp(closeTime / 1000)` and all numeric fields map from
    indices `1-5`. `trade_num` is taken from index `8` when available.

### USDⓈ-M futures (`usdm`)

- **WebSocket**: `wss://fstream.binance.com/stream?streams=<symbol>@kline_<interval>`
- **Backfill**: `GET https://fapi.binance.com/fapi/v1/klines`
- **Mapping**: identical to spot; the only difference is `contract_type="usdm"`.

### Coin-M futures (`coinm`)

- **WebSocket**: `wss://dstream.binance.com/stream?streams=<symbol>@kline_<interval>`
- **Backfill**: `GET https://dapi.binance.com/dapi/v1/klines`
- **Mapping**: identical to spot; `contract_type="coinm"`.

---

## Bybit

### Linear perpetual (`linear`)

- **WebSocket endpoint**: `wss://stream.bybit.com/v5/public/linear`
- **Subscription payload**:

  ```json
  {
    "op": "subscribe",
    "args": ["kline.1.<SYMBOL>", "..."]
  }
  ```

- **Stream response**:

  ```json
  {
    "topic": "kline.1.BTCUSDT",
    "ts": 1700000000000,
    "data": [
      {
        "symbol": "BTCUSDT",
        "interval": "1",
        "open": "44100",
        "high": "44150",
        "low": "44080",
        "close": "44123",
        "volume": "123.45",
        "tradeNum": 82,
        "confirm": false,
        "start": 1700000000000,
        "end": 1700000059999
      }
    ]
  }
  ```

- **Mapping**:

  | PriceQuote field   | Source                                                                 |
  |--------------------|------------------------------------------------------------------------|
  | `exchange`         | `"bybit"`                                                              |
  | `symbol`           | `entry["symbol"]` (fallback: topic suffix)                             |
  | `contract_type`    | `"linear"` (repository selector)                                       |
  | `timestamp`        | message `ts` if present, else candle `end/start` timestamps            |
  | `open`…`close`     | `float(entry[field])`                                                  |
  | `volume`           | `float(entry.get("volume", 0))`                                        |
  | `trade_num`        | `int(entry.get("tradeNum", 0))`                                        |
  | `is_closed_candle` | `bool(entry.get("confirm", False))`                                    |

- **REST backfill**: `GET https://api.bybit.com/v5/market/kline`

  - **Parameters**: `category=linear`, `symbol=<SYMBOL>`, `interval=<minutes>`, `limit=1`
  - **Response**: `{"result":{"list":[[start, open, high, low, close, volume, turnover, ...]]}}`
  - **Mapping**: the first row is converted; `timestamp` is `(start + interval_minutes*60*1000)`
    converted to UTC seconds. `is_closed_candle=True` for backfill snapshots.

### Inverse perpetual (`inverse`) & Spot (`spot`)

- **WebSocket endpoints**: `wss://stream.bybit.com/v5/public/inverse` and
  `wss://stream.bybit.com/v5/public/spot`.
- **Subscription / message / mapping**: identical to the linear feed.
- **REST backfill**: same endpoint with `category=inverse` or `category=spot`.

---

## Gate.io

### Spot (`spot`)

- **WebSocket endpoint**: `wss://api.gateio.ws/ws/v4/`
- **Subscription payload** (sent per symbol):

  ```json
  {
    "time": 1700000000,
    "channel": "spot.candlesticks",
    "event": "subscribe",
    "payload": ["1m", "<BASE_QUOTE>"]  // e.g. "BTC_USDT"
  }
  ```

- **Stream response**:

  ```json
  {
    "time": 1700000000,
    "channel": "spot.candlesticks",
    "event": "update",
    "result": {
      "t": "1700000000",
      "o": "44100",
      "h": "44150",
      "l": "44080",
      "c": "44123",
      "v": "123.45",
      "q": 80,
      "w": false,
      "n": "BTC_USDT"
    }
  }
  ```

- **Mapping**:

  | PriceQuote field   | Source                                                                 |
  |--------------------|------------------------------------------------------------------------|
  | `exchange`         | `"gateio"`                                                             |
  | `symbol`           | `result["currency_pair"]` / `result["contract"]` (normalised)          |
  | `contract_type`    | `"spot"`                                                               |
  | `timestamp`        | Derived from envelope `time_ms` or candle `t` + interval seconds       |
  | `open`…`close`     | `float(result[field])` (fields `o`, `h`, `l`, `c`)                     |
  | `volume`           | `float(result.get("a") or result.get("v"))`                            |
  | `trade_num`        | `int(result.get("q", 0))`                                              |
  | `is_closed_candle` | `bool(result.get("w", False))`                                         |

- **REST backfill**: `GET https://api.gateio.ws/api/v4/spot/candlesticks`

  - **Parameters**: `currency_pair=<SYMBOL>`, `interval=<INTERVAL>`, `limit=1`
  - **Response**: list of arrays `[time, volume, close, high, low, open, quoteVolume, finished]`
    or dictionaries with keys `o/h/l/c/v`. Mapping mirrors the WebSocket conversion.

### USDT-margined futures (`um`)

- **WebSocket endpoint**: `wss://fx-ws.gateio.ws/v4/ws/usdt`
- **Subscription**: same payload with `channel: "futures.candlesticks"` and `payload: ["1m", "<CONTRACT>"]`
- **REST backfill**: `GET https://api.gateio.ws/api/v4/futures/usdt/candlesticks`
- **Mapping**: identical to spot, `contract_type="um"`; symbols remain in Gate.io contract form (e.g. `BTC_USDT`).

### Coin-margined futures (`cm`)

- **WebSocket endpoint**: `wss://fx-ws.gateio.ws/v4/ws/{settle}` — the client replaces `{settle}` with the contract
  settle currency (e.g. `btc`).
- **REST backfill**: `GET https://api.gateio.ws/api/v4/futures/{settle}/candlesticks`
- **Mapping**: identical to the other Gate.io connectors; `contract_type="cm"`.

---

## OKX

### Candles for any instrument type (`contract_type` = optional OKX `instType`)

- **WebSocket endpoint**: `wss://ws.okx.com:8443/ws/v5/business`
- **Subscription payload**:

  ```json
  {
    "op": "subscribe",
    "args": [
      {"channel": "candle1m", "instId": "<INST_ID>"}
    ]
  }
  ```

- **Stream response**:

  ```json
  {
    "arg": {"channel": "candle1m", "instId": "BTC-USDT-SWAP", "instType": "SWAP"},
    "data": [
      ["1700000000000", "44100", "44150", "44080", "44123", "123.45", "0", "0", "1"]
    ]
  }
  ```

- **Mapping**:

  | PriceQuote field   | Source                                                         |
  |--------------------|----------------------------------------------------------------|
  | `exchange`         | `"okx"`                                                        |
  | `symbol`           | `arg["instId"]`                                                |
  | `contract_type`    | lower-case `arg["instType"]` (or configuration default)        |
  | `timestamp`        | `datetime.utcfromtimestamp(float(entry[0]) / 1000)`            |
  | `open`…`close`     | `float(entry[1])` … `float(entry[4])`                          |
  | `volume`           | `float(entry[5])`                                              |
  | `trade_num`        | Always `0` (not provided)                                      |
  | `is_closed_candle` | Value at index `8`/`7` interpreted as boolean (`"1"` = closed) |

- **REST backfill**: `GET https://www.okx.com/api/v5/market/candles`

  - **Parameters**: `instId=<INST_ID>`, `bar=<INTERVAL>`, `limit=1`, optionally `instType=<INST_TYPE>`
  - **Response**: `{"data": [["timestamp","open","high","low","close","volume",...]]}`
  - **Mapping**: identical to the WebSocket entry mapping.

---

## Summary

All connectors follow the same high-level process:

1. **WebSocket stream** delivers live candles; fields are parsed and normalised into
   the `PriceQuote` dataclass.
2. **Inactivity handling** kicks in after `CONNECTOR_INACTIVITY_TIMEOUT` seconds.
   The connector calls its REST **backfill** endpoint described above and converts the
   latest candle using the same mapping rules.
3. The `interfaces.ws_server` layer forwards these `PriceQuote` instances to external
   clients, and `test/run_all_ws_subscriptions.py` verifies every contract group by
   checking that at least one quote arrives (either live or via backfill).
