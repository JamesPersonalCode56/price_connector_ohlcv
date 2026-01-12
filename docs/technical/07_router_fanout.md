# Chapter 7 - Router and Fan-out

SubscriptionRouter:
- Shares a single upstream stream per (exchange, contract_type, symbol batch).
- Enforces max connections per exchange.
- Batches symbol lists to respect max symbols per connection.

SharedSubscription:
- Uses an internal pump task to broadcast quotes to subscribers.
- Handles per-subscriber queue overflow with QueueBackpressureError.
