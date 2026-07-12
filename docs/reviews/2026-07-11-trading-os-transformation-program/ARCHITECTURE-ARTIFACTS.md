# Architecture Artifacts

Reference diagrams and models for Phase 1–2. Implementation in Phase 5.

---

## 1. Bounded context map

```mermaid
flowchart TB
  subgraph presentation [Presentation]
    API[interface.api]
    UI[interface.ui]
    Agent[interface.agent]
  end

  subgraph operations [Operations / Control Plane]
    Lifecycle[Lifecycle]
    Cert[Certification]
    Readiness[Readiness]
  end

  subgraph decision [Decision / Research]
    Scanner[Scanner]
    Strategy[Strategy]
    Backtest[Backtest/Replay]
  end

  subgraph execution [Execution / Risk / OMS]
    OMS[Order Management]
    Risk[Risk]
    Ledger[Execution Ledger]
  end

  subgraph portfolio [Portfolio / Ledger]
    Position[Position Projection]
    PnL[PnL / Cash]
  end

  subgraph marketdata [Market Data]
    Feed[Feed Ingestion]
    Sub[Subscription SM]
    Norm[Normalization]
  end

  subgraph broker [Broker Integration]
    Wire[Wire Adapters]
    Auth[Auth / Token]
  end

  subgraph recon [Reconciliation]
    Compare[Drift Detection]
    Repair[Repair Commands]
  end

  subgraph domain [Domain Core]
    Agg[Aggregates + Events + Ports]
  end

  presentation --> execution
  presentation --> decision
  presentation --> marketdata
  decision -->|signals only| execution
  execution --> domain
  execution --> broker
  marketdata --> domain
  marketdata --> broker
  broker --> domain
  execution --> Ledger
  Ledger --> portfolio
  Ledger --> recon
  recon --> broker
  operations --> execution
  operations --> marketdata
  Backtest -->|reads events| domain
```

---

## 2. Package structure (target)

```
src/
├── domain/                 # Aggregates, VOs, commands, events, ports — ZERO outer imports
│   ├── entities/           # Order, Position, Trade, market entities
│   ├── executions/         # Execution aggregate root
│   ├── events/             # Event types, bus port
│   ├── instruments/        # Instrument, Subscription, resolver protocols
│   ├── orders/             # Intent, requests, execution plans
│   ├── market/             # SegmentMapper protocol + registry (no broker imports)
│   ├── ports/              # BrokerAdapter, TracingPort, repositories
│   └── reconciliation_engine.py
│
├── application/
│   ├── oms/                # OrderManager, TradingContext, risk, recon service
│   ├── execution/          # PlaceOrderUseCase, gateway_submit (injected)
│   ├── ledger/             # NEW P5: outbox, fill ingress, projections
│   ├── trading/            # Orchestrator (dispatcher-injected)
│   ├── streaming/          # StreamOrchestrator, tick router
│   └── composer/           # Gap reconciler, execution composer
│
├── infrastructure/         # Implements ports — no business decisions
│   ├── gateway/            # bootstrap_gateway (→ dynamic discovery P5)
│   ├── event_bus/
│   ├── persistence/
│   └── observability/      # Tracing adapter implements TracingPort
│
├── brokers/                  # Plugins: dhan, upstox, paper, common
│   ├── {broker}/wire.py    # WireAdapter implements BrokerAdapter
│   ├── certification/
│   ├── cli/ + mcp/
│   └── plugins/            # register_broker_plugin, segment mapper
│
├── runtime/                  # SINGLE composition root (target)
│   ├── factory.py          # NEW P5: build(mode, transport)
│   ├── commands/ + queries/
│   └── trading_runtime_factory.py  # → delegates to factory
│
├── tradex/                   # Thin public SDK
├── analytics/                # D2 isolated — no OMS imports
├── datalake/
└── interface/                # API, UI, agent — no broker internals
```

**Shim removal conditions:** documented per module in Handbook §5 (Phase 1 deliverable).

---

## 3. Dependency direction

```mermaid
flowchart BT
  domain[domain]
  application[application]
  infrastructure[infrastructure]
  brokers[brokers]
  runtime[runtime]
  interface[interface]
  analytics[analytics]
  tradex[tradex]

  application --> domain
  infrastructure --> domain
  brokers --> domain
  analytics --> domain
  runtime --> application
  runtime --> infrastructure
  runtime --> brokers
  tradex --> runtime
  interface --> runtime
  interface --> application

  application -.->|FORBIDDEN| brokers
  domain -.->|FORBIDDEN| brokers
  analytics -.->|FORBIDDEN| application.oms
```

Enforced by `pyproject.toml` import-linter (15 contracts). Target: **15/15 pass** after TRANS-P3-008.

---

## 4. Domain model (aggregates)

### Order

| Attribute | Type | Notes |
|-----------|------|-------|
| order_id | str | Internal |
| correlation_id | str | Idempotency key |
| status | OrderStatus | Includes UNKNOWN |
| side, qty, price | VOs | Decimal |
| filled_qty | Decimal | Cumulative |

**Invariants:** Legal transitions per state machine; UNKNOWN blocks retry until recon.

### Execution (aggregate root)

| Responsibility | Method |
|----------------|--------|
| Own fills for one order | `apply_trade(trade)` |
| Compute averages | `avg_price()`, `filled_quantity()` |
| Emit fact | `TRADE_APPLIED` event |

**Invariant:** No double-application of same trade_id.

### Position

| Responsibility | Notes |
|----------------|-------|
| Quantity, avg price | From fills only |
| Realized PnL | On reducing fills |
| State machine | `PositionState` transitions |

### Subscription

| State | Meaning |
|-------|---------|
| inactive | Created, not attached |
| active | Receiving ticks |
| degraded | Stale or dropping |
| ended | Unsubscribed |

**Invariant:** `is_active()` false when degraded (target — Phase 5).

### BrokerSession

| State | Meaning |
|-------|---------|
| authenticated | Token valid |
| read_only | Data only |
| trading_enabled | Orders allowed |
| degraded | Partial capabilities |
| closed | Shutdown |

### TradingAccount (risk)

| Attribute | Notes |
|-----------|-------|
| available_capital | Reservations subtract |
| daily_pnl | Boundary reset |
| kill_switch | Blocks new orders |

---

## 5. Event model (catalog summary)

### Commands (intent, synchronous boundary)

| Command | Handler owner | Response |
|---------|---------------|----------|
| PlaceOrder | OMS | ACCEPTED / REJECTED / UNKNOWN |
| CancelOrder | OMS | Same |
| ReconcileAccount | Reconciliation | DriftReport |
| StartSubscription | Market Data | Subscription handle |
| StopSubscription | Market Data | Ack |
| RunStrategy | Orchestrator | Signal batch (no direct order) |

### Domain events (facts)

| Event | Producer | Consumers |
|-------|----------|-----------|
| OrderIntentAccepted | OMS | Audit, ledger |
| RiskApproved / RiskRejected | Risk | OMS |
| OrderSubmitted | OMS | Ledger, recon |
| OrderSubmissionUnknown | OMS | Recon (expedited) |
| OrderPartiallyFilled / OrderFilled | OMS / stream | Portfolio |
| TradeApplied | Execution | Position |
| QuoteReceived / DepthUpdated | Market Data | Analytics, UI |
| SubscriptionDegraded | Market Data | Readiness |
| ReconciliationDriftDetected | Reconciliation | Control plane |
| PositionChanged | Portfolio | Risk |

### Event envelope (target — TRANS-P5-034)

```
event_id, schema_version, aggregate_id, correlation_id, causation_id,
occurred_at, source, mode, sequence, payload
```

---

## 6. Runtime architecture

```mermaid
flowchart TB
  subgraph entry [Entry Points]
    SDK[tradex.connect]
    CLI[broker / tradex CLI]
    API[FastAPI]
    MCP[MCP server]
  end

  subgraph root [runtime.factory.build]
    Factory[RuntimeFactory]
    Ctx[TradingContext]
    Bus[EventBus]
    Disp[CommandDispatcher]
    Life[LifecycleManager]
  end

  subgraph app [Application Services]
    OMS[OrderManager]
    Orch[TradingOrchestrator]
    Recon[ReconciliationService]
    Stream[StreamOrchestrator]
  end

  subgraph ledger [Execution Ledger P5]
    Outbox[Outbox]
    FillIn[Fill Ingress]
    Proj[Projections]
  end

  entry --> Factory
  Factory --> Ctx
  Factory --> Bus
  Factory --> Disp
  Factory --> Life
  Ctx --> OMS
  Ctx --> Recon
  Disp --> OMS
  OMS --> ledger
  Bus --> Orch
  Bus --> Stream
```

**Current state:** 6+ roots → **target:** all entry points call `runtime.factory.build()`.

---

## 7. Plugin architecture

```mermaid
flowchart LR
  EP[pyproject.toml entry_points tradex.brokers]
  EP --> Import[import brokers.dhan]
  Import --> Reg[register_broker_plugin]
  Reg --> Meta[BrokerPlugin metadata]
  Reg --> Seg[SegmentMapperRegistry.register]
  Reg --> Exec[register_execution_provider]
  Meta --> Factory[Gateway factory discovery]
  Wire[wire.py BrokerAdapter] --> Cert[BrokerCertifier]
```

**Adding broker `foo` (target):**
1. `pyproject.toml` entry point
2. `brokers/foo/{__init__,wire,factory}.py`
3. Certification suite pass
4. **Zero** edits to `domain/`, `application/oms/`

---

## 8. Key flow sequence — PlaceOrder

```mermaid
sequenceDiagram
  participant C as Client
  participant D as CommandDispatcher
  participant UC as PlaceOrderUseCase
  participant O as OrderManager
  participant L as OrderLifecycle
  participant LD as Ledger
  participant W as WireAdapter
  participant B as EventBus

  C->>D: PlaceOrderCommand
  D->>UC: execute
  UC->>O: place_order
  O->>O: idempotency + risk
  O->>L: submit_to_broker
  L->>LD: record_intent
  L->>W: submit
  alt success
    W-->>L: ack
    L->>LD: record_outcome ACCEPTED
    L->>B: ORDER_PLACED
  else ambiguous
    W-->>L: exception
    L->>LD: record_outcome UNKNOWN
    L->>B: ORDER_UPDATED unknown
  end
```

---

## 9. ADR plan

| ADR | Title | Phase | Status |
|-----|-------|-------|--------|
| ADR-012 | CQRS dispatchers | Done | Accepted |
| ADR-013 | Broker set | Done | Accepted |
| ADR-014 | Persistence | Done | Accepted |
| ADR-014-brokers | Trading OS mini-OS | Done | Accepted |
| ADR-015 | Execution ledger authority | P1 | **To write** |
| ADR-016 | Market data EventBus canonical path | P1 | **To write** |
| ADR-017 | Single composition root | P1 | **To write** |
| ADR-018 | Certification truth tiers | P1 | **To write** |
| ADR-019 | CI gate semantics | P3 | **To write** |
| ADR-020 | Deployment topology (single-writer) | P7 | Planned |
| ADR-021 | Event envelope versioning | P5 | Planned |

Existing: `docs/architecture/adrs/`