# ADR-002: MarketDataGateway is the Frozen Contract

## Context
The `MarketDataGateway` ABC in `brokers/common/gateway.py` defines the broker-agnostic interface that all broker adapters (Dhan, Upstox, Paper, DataLake) must implement. The SPI ports in `brokers/common/api/ports.py` define fine-grained capability contracts.

## Decision
- `MarketDataGateway` is the coarse-grained facade — the single interface consumers use
- SPI ports (`OrderCommand`, `OrderQuery`, `MarketDataProvider`, etc.) are the fine-grained building blocks that broker adapters implement internally
- The gateway delegates to ports internally; consumers never import ports directly
- The gateway contract is versioned (v1.0) and frozen — adding methods requires a major version bump

## Consequences
- New broker implementations must implement every MarketDataGateway method
- Broker-specific methods (e.g., `expired_option_chain`) belong on the broker's connection object, not the gateway
- The IntelligentGateway composes multiple gateways through the same interface
