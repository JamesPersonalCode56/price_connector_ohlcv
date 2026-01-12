# Chapter 1 - Overview

This guide explains how to use the OHLCV Python Connector to stream 1-minute candle data
from multiple exchanges via a local WebSocket server. It covers setup, configuration,
operation, troubleshooting, and common workflows.

Key capabilities:
- Multi-exchange OHLCV streaming with a single WebSocket endpoint.
- Automatic reconnects and optional REST backfill when streams are idle.
- Health and readiness endpoints with Prometheus metrics.
- Clean Architecture design with modular exchange connectors.
