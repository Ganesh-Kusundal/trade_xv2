# Trading OS Glossary

**Version:** 1.0 (TRANS-P1-003)

| Term | Definition |
|------|------------|
| **Trading OS** | Trade_XV2 platform: broker-agnostic execution, market data, and operations kernel. |
| **Bounded context** | DDD ownership boundary (OMS, Market Data, Broker Integration, …). |
| **Composition root** | Module that wires ports to adapters (`runtime`, `tradex.open_session`). |
| **Broker plugin** | Entry-point registered package (`dhan`, `upstox`, `paper`) implementing wire + capabilities. |
| **Wire adapter** | `brokers.<id>.wire` — translates domain requests to broker HTTP/WS payloads. |
| **BrokerSession** | Public SDK handle for authenticated broker connectivity (ADR-014). |
| **SegmentMapper** | Bidirectional `ExchangeSegment` ↔ broker wire segment string. |
| **SegmentMapperRegistry** | Domain-owned lookup; brokers register at import via entry point. |
| **TradingContext** | Process-scoped OMS container (`application.oms.process_context`). |
| **OrderManager** | Application service owning in-memory order book + lifecycle coordination. |
| **Execution ledger** | Authoritative outbox for money-moving facts (ADR-015, Phase 5). |
| **UNKNOWN** | Order status when broker outcome is ambiguous; blocks retry until recon. |
| **EventBus** | In-process pub/sub for `DomainEvent` facts (`domain.events`). |
| **Command** | Imperative boundary DTO (`PlaceOrder`, `CancelOrder`) via CQRS dispatchers. |
| **Domain event** | Past-tense fact (`ORDER_PLACED`, `TRADE_APPLIED`) with typed payload. |
| **Projection** | Read model derived from ledger/events (positions, portfolio). |
| **Reconciliation** | Compare broker truth vs local book; emit `RECONCILIATION_DRIFT`. |
| **Certification** | `broker verify` / `broker certify` matrix proving broker contract. |
| **Doctor** | Health probe command (`broker doctor`) — advisory in CI until P4. |
| **Parity mode** | Replay/backtest using same handlers as live with simulated I/O. |
| **Fail closed** | Prefer explicit error/UNKNOWN over silent success or stale data. |
| **Advisory gate** | CI step that may fail without blocking merge (ADR-019). |
| **Blocking gate** | CI step that must pass for merge (import-linter, arch tests, unit). |
| **HistoricalBar** | Domain SSOT for one OHLCV bar — Decimal OHLC, UTC `event_time`, provenance. |
| **HistoricalSeries** | Domain collection of `HistoricalBar` with coverage, gaps, merge manifest. |
| **MarketTick** | Domain SSOT for one live market tick (LTP, volume, provenance). |
| **InstrumentRef** | Minimal `{symbol, exchange}` identity attached to bars. |
| **Bar label convention** | Whether broker timestamp is bar open (LEFT), close (RIGHT), or center. |
| **Data provenance** | Lineage record (`DataProvenance`) on normalized market artifacts. |
| **API candle** | Wire-only Pydantic `Candle` (`t/o/h/l/c/v/oi`); not a domain type. |
| **Datalake candle** | Parquet storage row; naive IST timestamp; ingress via `from_datalake_df`. |
| **Analytics OHLCV frame** | pandas working set for `FeaturePipeline`; export of `HistoricalSeries`. |
| **Degraded series** | `HistoricalSeries` with partial data / gaps; must be observable, not silent. |
| **Partial bar** | `HistoricalBar.is_partial=True` — live candle still forming. |
| **Zero-parity** | Backtest, replay, lake, and live paths must use the same domain bar semantics. |
| **TradingIntent** | Pre-risk desire to trade (`domain.orders.intent.OrderIntent`). Alias preferred in new code. |
| **PersistedOrderIntent** | Durable ledger command before broker I/O (`domain.execution_contracts.OrderIntent`). |
| **BrokerAdapter** | App-facing Protocol for data+execution (ADR-021). |
| **BrokerTransport** | Wire/reconnect ABC — not the OMS order path (ADR-021). |
| **MarketSurface** | Exchange/currency/tick conventions SSOT (`market_data.market_surface`). |
| **OrderCapabilityPort** | OMS extension port for super/GTT/etc. — broker-agnostic (DR-B1). |
