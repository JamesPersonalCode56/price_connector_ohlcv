# Chapter 6 - Repository and Contract Type Resolution

WebSocketPriceFeedRepository:
- Builds a config object per exchange/contract type.
- Instantiates the exchange client and delegates streaming.

ContractTypeResolver:
- Maps aliases and defaults to canonical contract types.
- Provides a clear error message when unsupported.
