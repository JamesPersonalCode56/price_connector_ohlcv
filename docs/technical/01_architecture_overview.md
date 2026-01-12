# Chapter 1 - Architecture Overview

The connector follows Clean Architecture with explicit layering:
- domain: core entities and repository interfaces
- application: use cases (business logic)
- infrastructure: exchange clients and shared systems
- interfaces: entry points (WebSocket server, health server)

Data flow:
Exchange WebSocket -> client parse -> repository -> router -> server -> client
If idle: REST backfill -> parse -> same pipeline
