# 01 — Architecture High-Level Design

## 1. Design Philosophy

TradeXV2 follows a **NautilusTrader-inspired** layered architecture where the entire
system is decomposed into six concentric rings. Each ring depends only on the rings
inside it — never on the rings outside. This is enforced at CI time by
`import-linter` contracts.

```
┌─────────────────────────────────────────────────────────────────────┐
│  INTERFACE   cli/  tui/  api/  mcp/                                │
│  ─────────────────────────────────────────────────────────────────  │
│  RUNTIME     runtime/  (composition root, lifecycle, wiring)       │
│  ─────────────────────────────────────────────────────────────────  │
│  INFRA       infrastructure/  (brokers, datalake, persistence)     │
│  ─────────────────────────────────────────────────────────────────  │
│  APPLICATION application/  (engines, managers, orchestrators)      │
│  ─────────────────────────────────────────────────────────────────  │
│  DOMAIN      domain/  (entities, value objects, events, ports)     │
│  ─────────────────────────────────────────────────────────────────  │
│  SHARED      shared/  (logging, config, types, utils)              │
└─────────────────────────────────────────────────────────────────────┘
```

## 2. Layer Responsibilities

### 2.1 Domain Layer (`domain/`)

The innermost ring. Contains **zero** framework imports.

| Sub-module | Contents |
|---|---|
| `domain/entities/` | `Order`, `Position`, `Trade`, `Quote`, `MarketDepth`, `OptionChain`, `Instrument` |
| `domain/value_objects/` | `Money`, `Quantity`, `Price`, `Symbol`, `Exchange`, `InstrumentId` |
| `domain/events/` | `DomainEvent`, `OrderPlaced`, `OrderFilled`, `PositionChanged`, `RiskBreached` |
| `domain/commands/` | `PlaceOrderCommand`, `CancelOrderCommand`, `ModifyOrderCommand` |
| `domain/ports/` | `BrokerAdapterPort`, `FillSourcePort`, `EventBusPort`, `DataCatalogPort`, `RiskEnginePort` |
| `domain/services/` | `PricingService`, `FeeCalculator`, `InstrumentRegistry` |
| `domain/policies/` | `SourceSelectionPolicy`, `RoutingPolicy` |

**Invariants:**
- No imports from `application/`, `infrastructure/`, `runtime/`, or `interface/`.
- All external dependencies expressed as `Protocol` classes (ports).
- Entities are plain dataclasses — no ORM, no I/O.

### 2.2 Application Layer (`application/`)

Contains orchestration logic — the "how" of the system.

| Sub-module | Contents |
|---|---|
| `application/execution/` | `ExecutionEngine`, `FillSource` implementations |
| `application/oms/` | `OrderManager`, `PositionManager`, `TradingContext` |
| `application/risk/` | `RiskManager`, `RiskRules`, `KillSwitch` |
| `application/strategy/` | `StrategyEngine`, `StrategyBase`, `SignalGenerator` |
| `application/streaming/` | `LiveTickPipeline`, `StreamOrchestrator` |
| `application/analytics/` | `ViewManager`, `AnalyticsEngine` |

**Invariants:**
- May import from `domain/` and `shared/` only.
- No HTTP, no database drivers, no broker SDKs.
- All I/O via domain ports.

### 2.3 Infrastructure Layer (`infrastructure/` — currently `brokers/` + `datalake/`)

Concrete implementations of domain ports.

| Sub-module | Contents |
|---|---|
| `brokers/dhan/` | `DhanGateway`, `DhanConnection`, wire adapters |
| `brokers/upstox/` | `UpstoxGateway`, `UpstoxConnection`, websocket v3 |
| `brokers/paper/` | `PaperGateway`, `PaperConnection`, simulated fills |
| `brokers/common/` | `BaseWireAdapter`, `BaseTransport`, shared helpers |
| `datalake/` | `DataCatalog`, DuckDB engine, Parquet I/O, sync |

**Invariants:**
- May import from `domain/`, `application/` (for port types), and `shared/`.
- Owns all third-party SDK dependencies.
- Each broker is a self-contained sub-package discoverable via entry points.

### 2.4 Runtime Layer (`runtime/`)

The composition root — where objects are created and wired.

| Sub-module | Contents |
|---|---|
| `runtime/composition/` | `ComponentRegistry`, `ComponentFactory` |
| `runtime/lifecycle/` | `LifecycleManager`, startup/shutdown sequences |
| `runtime/config/` | `ConfigManager`, YAML loader, env overlay |
| `runtime/broker_infrastructure/` | `BrokerInfrastructure` (degree 13 today) |

**Invariants:**
- Only layer that knows about ALL other layers.
- No business logic — pure wiring.
- Single entry point: `bootstrap(config_path) -> TradingContext`.

### 2.5 Interface Layer (`interface/`)

User-facing surfaces.

| Sub-module | Contents |
|---|---|
| `interface/cli/` | Click/Typer commands |
| `interface/tui/` | Textual/rich terminal UI |
| `interface/api/` | FastAPI REST + WebSocket |
| `interface/mcp/` | MCP server for AI tool integration |

**Invariants:**
- May import from `runtime/` and `application/` only.
- No direct domain or infrastructure imports.
- Thin — delegates immediately to application services.

### 2.6 Shared Layer (`shared/`)

Cross-cutting utilities used by all layers.

| Sub-module | Contents |
|---|---|
| `shared/logging/` | Structured logging, log context |
| `shared/config/` | `BaseSettings`, env helpers |
| `shared/types/` | Common type aliases, NewTypes |
| `shared/errors/` | Exception hierarchy |

## 3. Dependency Rules (import-linter)

```ini
[importlinter]
root_packages = domain, application, infrastructure, runtime, interface, shared

[importlinter:contract:1]
name = Domain has no outer imports
type = forbidden
source_modules = domain
forbidden_modules = application, infrastructure, runtime, interface

[importlinter:contract:2]
name = Application depends only on Domain + Shared
type = forbidden
source_modules = application
forbidden_modules = infrastructure, runtime, interface

[importlinter:contract:3]
name = Infrastructure depends on Domain + Application ports
type = forbidden
source_modules = infrastructure
forbidden_modules = runtime, interface

[importlinter:contract:4]
name = Runtime is the composition root
type = forbidden
source_modules = interface
forbidden_modules = infrastructure  # must go through runtime

[importlinter:contract:5]
name = Brokers are isolated from each other
type = independence
modules = infrastructure.brokers.dhan, infrastructure.brokers.upstox, infrastructure.brokers.paper
```

## 4. Key Architectural Decisions

### ADR-001: Message-Driven over Direct Calls
**Decision:** All inter-component communication goes through `MessageBus`.
**Rationale:** Enables zero-parity (same code for backtest/live), decouples components, provides natural audit trail.
**Consequence:** Slightly higher latency per call; mitigated by in-process bus (no serialization for same-process messages).

### ADR-002: Gateway → Connection → Sub-Adapters
**Decision:** Each broker follows `Gateway → Connection → {OrdersAdapter, MarketDataAdapter, PortfolioAdapter, InstrumentAdapter, StreamingAdapter}`.
**Rationale:** Eliminates god classes (DhanBroker has degree 376 today). Each adapter is independently testable.
**Consequence:** More files, but each is small and focused.

### ADR-003: FillSource Protocol for Zero-Parity
**Decision:** `FillSource` protocol with three implementations: `SimulatedFillSource`, `PaperFillSource`, `BrokerFillSource`.
**Rationale:** Same OMS + Risk logic across all modes. Only the fill source changes.
**Consequence:** Backtest results are directly comparable to live performance.

### ADR-004: Plugin Discovery via Entry Points
**Decision:** Brokers and exchanges register via `pyproject.toml` entry points (`tradex.brokers`, `tradex.exchanges`).
**Rationale:** Adding a new broker requires zero changes to core code. Enables third-party broker plugins.
**Consequence:** Slightly more complex bootstrap; mitigated by `BrokerPlugin` registry.

### ADR-005: DuckDB + Parquet for Data Lake
**Decision:** DuckDB as analytical engine, Parquet as storage format.
**Rationale:** Columnar storage ideal for OHLCV time series. DuckDB provides SQL interface without a server. Zero operational overhead.
**Consequence:** Not suitable for real-time tick storage; use in-memory ring buffer for live ticks.

### ADR-006: Component Lifecycle State Machine
**Decision:** Every component implements `UNINITIALIZED → INITIALIZED → RUNNING → STOPPED` with valid transitions only.
**Rationale:** Prevents use-before-init, double-start, and use-after-stop bugs. Mirrors NautilusTrader's `Component` base class.
**Consequence:** Components must be lifecycle-aware; adds boilerplate mitigated by `Component` base class.

### ADR-007: Instrument Ref Isolation
**Decision:** Wire-level identifiers (`DhanInstrumentRef`, `UpstoxInstrumentRef`) never leak to gateway callers. Callers use `(symbol, exchange)` tuples.
**Rationale:** Callers should be broker-agnostic. Swapping brokers should not require caller changes.
**Consequence:** `SymbolResolver` adds a lookup step; negligible cost.

### ADR-008: Immutable Domain Events
**Decision:** All domain events are frozen dataclasses with `timestamp`, `correlation_id`, and `source`.
**Rationale:** Enables reliable event sourcing, replay, and audit. Immutable events prevent accidental mutation.
**Consequence:** More memory usage; mitigated by periodic compaction.

## 5. System Invariants

These invariants MUST hold at all times and are enforced by tests:

1. **Layer Purity:** No layer imports from a layer outside its allowed set (enforced by import-linter in CI).
2. **No God Classes:** No single class may have degree > 50 in the dependency graph (enforced by graphify check).
3. **Zero-Parity:** The same `ExecutionEngine` code path must work for backtest, paper, and live — only the `FillSource` injection differs.
4. **Event Completeness:** Every state change in the OMS emits exactly one domain event.
5. **Lifecycle Safety:** No component may receive messages before `initialize()` or after `stop()`.
6. **Instrument Isolation:** No broker wire type may appear in `domain/` or `application/` type signatures.
7. **Idempotent Fills:** Applying the same fill twice must produce the same position state.
8. **Risk Before Broker:** Every order must pass risk check before reaching the fill source.

## 6. Comparison with Current State

| Aspect | Current (graphify-validated) | Target V2 |
|---|---|---|
| Layers | Flat `src/` with some structure | 6 strict layers, CI-enforced |
| Biggest class | `DhanBroker` (degree 376) | Max degree 50 |
| Broker pattern | Monolithic wire adapter | Gateway → Connection → 5 sub-adapters |
| Inter-component calls | Direct method calls | MessageBus (typed, traceable) |
| Backtest vs Live | Separate code paths | Zero-parity via FillSource |
| Config | Scattered env vars | Declarative YAML + env overlay |
| Testing | Ad hoc | Adapter harness + parity tests |
| Observability | print + logger | Structured logs + metrics + traces |

## 7. Migration Path

```
Phase 1 (Weeks 1-4):   Domain layer extraction + import-linter CI
Phase 2 (Weeks 5-8):   MessageBus + Component lifecycle base
Phase 3 (Weeks 9-12):  Broker adapter framework (Gateway→Connection→Adapters)
Phase 4 (Weeks 13-16): Execution engine + FillSource zero-parity
Phase 5 (Weeks 17-20): Data engine + DataLake integration
Phase 6 (Weeks 21-24): Strategy system + backtest/replay/paper unification
Phase 7 (Weeks 25-28): Observability + config + plugin system
Phase 8 (Weeks 29-32): Migration of existing strategies + production hardening
```

Each phase produces a working system. No phase requires the next phase to be useful.
