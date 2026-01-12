# Chapter 5 - Subscription Payload

Required fields:
- exchange: string, name of exchange (binance, okx, bybit, gateio, hyperliquid).
- symbols: list of strings, symbol list.

Optional fields:
- contract_type: string, depends on exchange.
- limit: integer >= 0, number of messages to send before closing (0 = no limit).

Notes:
- Binance requires contract_type.
- Some exchanges default to a contract_type if not provided.
