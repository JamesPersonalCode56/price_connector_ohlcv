# Chapter 14 - Extension Guide

To add a new exchange:
1) Implement a client inheriting WebSocketPriceFeedClient.
2) Add a repository that builds the client config.
3) Update exchange_config with endpoint metadata.
4) Register in repository_factory.
5) Add integration tests for a known symbol.
