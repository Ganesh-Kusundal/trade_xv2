# Bounded Contexts and Ownership

## Target contexts

### Domain

Owns instrument identity, orders, fills, positions, accounts, lifecycle enums, value objects, and domain events. It contains no broker, analytics, UI, or infrastructure implementation.

### Market Data

Owns broker feed ingestion, normalization, validation, event time, sequence/gap tracking, aggregation, storage, and replay event sourcing. It never creates orders or mutates portfolio state.

### Decision and Research

Owns features, scanners, strategies, signal decisions, walk-forward evaluation, and research metrics. It emits decisions only; it cannot call `OrderManager`, broker gateways, or mutate positions.

### Execution and Risk

Owns risk reservations, order intent persistence, submission outcome handling, fill application, position/cash/PnL projections, and emergency-exit policy. This is the only context allowed to mutate money-moving state.

### Broker Integration

Owns authentication wire details, endpoint mapping, status/price/time decoding, stream lifecycle, and broker capability declarations. It implements domain ports and cannot own portfolio truth.

### Reconciliation and Control Plane

Owns broker-truth comparison, discrepancies, recovery, readiness, leases, audit durability, authorization, and operational controls.

### Presentation

Owns API, CLI, TUI, WebSocket subscription intent, projections, and user commands. It cannot directly manage broker stream lifecycle or execute hidden fallback orders.

## Ownership table in prose

- **Order lifecycle:** `application.execution` execution ledger/projector.
- **Fill identity and application:** execution ledger reducer.
- **Position/PnL/cash:** portfolio projection derived from committed fills.
- **Risk reservations:** execution/risk partition, atomically coupled to order intent.
- **Broker truth:** broker adapter plus reconciliation input; never a local replacement for broker truth.
- **Market-data freshness:** market-data pipeline; readiness consumes its state.
- **Strategy state:** strategy context keyed by strategy/version/instrument; never embedded in broker or OMS.
- **Audit:** durable infrastructure append, with order intent and control-plane mutation as transactional producers.
- **Readiness:** one control-plane evaluator used by runtime, API, CLI, and order routes.

## Current-to-target conflict map

- `OrderManager`, `PaperOrders`, `PaperSession`, `ReplaySession`, and `FastBacktestEngine` currently own overlapping order/trade/position state. Only the execution ledger and projections may remain authoritative.
- `EventLog`, `ProcessedTradeRepository`, and `SqliteOrderStore` each persist a partial slice. They become storage components behind one ledger contract rather than separate truths.
- Broker gateways, `BrokerTransport`, `ExecutionProvider`, and `BrokerAdapter` coexist. The port contract becomes the stable seam; compatibility facades remain only during migration.
- Broker feeds, `StreamOrchestrator`, and API WebSocket wiring each perform ingestion/fan-out. Feed ingestion becomes canonical; API/UI consume validated projections and subscription intents.

## Dependency rules

1. Domain depends on nothing outside domain and standard library.
2. Analytics depends on domain data/contracts, never OMS/execution or concrete brokers.
3. Application depends on domain ports and policies, never concrete broker modules.
4. Infrastructure implements ports and persistence, never owns business decisions.
5. Broker adapters depend on domain ports and common transport/ACL, never on another broker.
6. Presentation depends on application ports/projections, never private broker attributes.
7. All cross-context mutations are typed commands/events with versioned contracts.
