# Current-to-Target Migration Matrix

## Execution and state

**Current:** `OrderManager`, `TradeRecorder`, `PositionManager`, `PaperOrders`, `PaperSession`, `ReplaySession`, and `FastBacktestEngine` each own slices of economic state.  
**Target owner:** execution ledger and projections.  
**Migration:** add ledger append/projector behind the current live OMS; emit dual projections; migrate replay/backtest; migrate Paper; delete shadow collections only after parity and restart evidence.  
**Compatibility shim:** current `TradingContext` and `ExecutionService` APIs.  
**Deletion condition:** no caller reads or mutates mode-local order/trade/position state.

## Event persistence and idempotency

**Current:** `EventLog`, `ProcessedTradeRepository`, and `SqliteOrderStore` persist partial lifecycle state.  
**Target owner:** ledger storage with event identity, schema version, checkpoint, and projection version.  
**Migration:** preserve existing repositories as adapters/readers; backfill only with verified IDs; run restart reconstruction before removing them.  
**Deletion condition:** recovery can rebuild identical positions/PnL from ledger alone.

## Broker contract

**Current:** `BrokerAdapter`, legacy gateways, `ExecutionProvider`, and `BrokerTransport` coexist.  
**Target owner:** typed domain port plus broker ACL.  
**Migration:** contract-test each method, route one use case at a time through ACL, retain gateway shim with telemetry.  
**Deletion condition:** repository-wide call-site search shows no deep gateway/private access and live/sandbox contract evidence is green.

## Reconnect and retry

**Current:** common transport, Dhan feed-local loops, Dhan mixins, Upstox stream loops, and generic retry executors.  
**Target owner:** one operation-aware transport/resilience policy per lifecycle partition.  
**Migration:** wrap existing loops with policy metrics first; migrate Dhan; then Upstox; retain old loop only as a disabled compatibility path during soak.  
**Deletion condition:** reconnect, token refresh, subscription replay, stale detection, shutdown, and cancellation tests pass through one owner.

## Market data

**Current:** broker publishers, `StreamOrchestrator`, and API feed wiring can all ingest/fan out.  
**Target owner:** canonical validated market-data pipeline.  
**Migration:** route one broker feed through canonical envelope; API uses subscription registry and projections; add sequence/gap metrics.  
**Deletion condition:** no API/UI path calls broker `stream()` directly and resync works after queue drops.

## Capabilities

**Current:** capability snapshots, transport capability enums, gateway registries, and market surfaces can disagree.  
**Target owner:** declarative `BrokerCapabilities.market_surfaces` plus wire support declarations.  
**Migration:** add executable probes/contract rows for every declared surface; mark unsupported rather than advertising synthetic behavior.  
**Deletion condition:** one capability query drives routing, UI, and contract coverage.

## Readiness and control plane

**Current:** health registry, broker monitor, production readiness, API readiness, and gateway state each report partial truth.  
**Target owner:** unified readiness evaluator with liveness/readiness/tradability views.  
**Migration:** compose existing checks into one typed result; make new-entry routes consume it; preserve health endpoints as projections.  
**Deletion condition:** all runtime entry points use the same readiness decision and failure evidence.

## Security and audit

**Current:** shared API keys, optional token encryption, unsigned token webhook, fire-and-forget audit.  
**Target owner:** scoped authorization, mandatory protected secret store, signed ingestion, durable audit.  
**Migration:** introduce dual-auth verification and audit before mutation; reject insecure production configuration after operator migration.  
**Deletion condition:** no production path accepts plaintext/unsigned/shared-admin mutation.

## Persistence and scale

**Current:** SQLite single-writer assumption and module-level mutable services.  
**Target owner:** account/strategy partition lease plus durable ordered ledger.  
**Migration:** enforce single-writer lease first; measure load; replace storage only after partition contract is tested.  
**Deletion condition:** deployment topology and recovery drill demonstrate one authoritative writer per partition.
