# Baseline Architecture — TradeXV2

> **Source of truth:** reverse-engineered from code + graphify (`graphify-out/`, commit snapshot at audit time).
> Existing `docs/architecture/AUDIT-*` and e2e-spec docs were **not** used as inputs.
> Date: 2026-07-17 (re-baselined per GOV-4).

---

## 1. System Intent

TradeXV2 is a **real-money trading operating system**. It must:

1. Run strategy signals through a **single order spine** across three modes — **backtest**, **replay**, and **live** — with identical P&L and state math (**zero-parity**).
2. Enforce **fail-closed** risk gates, **order idempotency**, and **broker reconciliation** before any live order is actionable.
3. Keep a clean hexagonal layering: `domain` (ports + model) ← `application` ← adapters (`infrastructure`, `brokers`), with `interface` (API/UI) as the composition-root leaf.

---

## 2. Package Map (as-built)

| Package | LOC (approx) | Role |
|---|---|---|
| `src/domain/` | ~22.6k | Entities, VOs, enums, domain services, **ports** (~40 Protocols) |
| `src/application/` | ~16.9k | OMS, execution, risk, trading orchestrator, multi-strategy runtime |
| `src/brokers/` | ~42.4k | Market-access adapters (Dhan, Upstox, paper) + certification + CLI services |
| `src/infrastructure/` | ~16.9k | EventBus, gateway factory, resilience, idempotency, observability, auth |
| `src/analytics/` | ~18.0k | Backtest / replay / paper engines, strategy pipeline, indicators |
| `src/interface/` | ~21.8k | FastAPI routers + CLI/UI services (composition-ish) |
| `src/runtime/` | ~2.0k | `TradingRuntimeFactory`, broker builders, CQRS dispatchers |
| `src/tradex/` | ~1.1k | SDK session entry (`open_session`) — **second** composition root |
| `src/datalake/` | ~9.3k | Historical storage, exchange registry, quality monitor |

```
interface/ (API + UI) ── composition root, but INVERTED (API → UI imports)
        │  service-locator string DI; module-global session state
        ▼
application/ (OMS, execution, risk, trading) ── imports infrastructure (layer break)
        │
   ┌────┴─────────────┬──────────────────┐
   ▼                  ▼                  ▼
domain/             infrastructure/    brokers/
(ports + VOs;       (EventBus,         (DhanWireAdapter /
 CLEAN — 0          gateway factory,    UpstoxWireAdapter
 outward imports)   resilience)         behind BrokerAdapter)
        ▲
analytics/ (backtest / replay / paper — THREE divergent engines;
            shared StrategyPipeline + FeaturePipeline)
```

Graphify hubs that match this map: `EventBus`, `OrderManager`, `RiskManager`, `TradingRuntimeFactory`, `ReplayEngine`, `PaperTradingEngine`, `BrokerService`, `FeaturePipeline`, `Signal`.

---

## 3. Domain Model (innermost)

### 3.1 What is sound

- **Zero outward imports** from `src/domain` into `brokers` / `infrastructure` / `interface` / `application` (verified by grep).
- Ports live in `src/domain/ports/` (`BrokerAdapter`, `EventBusPort`, `RiskManagerPort`, `OmsBacktestAdapterPort`, `ExecutionLedgerPort`, observability, etc.).
- Strong value objects: `Money`, `Quantity`, `Clock` in `src/domain/primitives/value_objects.py` (Decimal, frozen, injected clock).
- Entities: `Order`, `Trade`, `Position` with immutable `with_*` transitions; `Order.with_status` enforces `ORDER_STATUS_TRANSITIONS`.
- Thin aggregates: `PositionAggregate`, `AccountAggregate` (lock + VO).

### 3.2 What is fragmented

| Concept | Locations | Notes |
|---|---|---|
| `OrderRequest` | `domain/orders/requests.py` vs `OmsOrderCommand` (`application/oms/order_manager.py`, aliased `OrderRequest`) | Different shapes (`transaction_type` vs `side`) |
| `Trade` / `Position` | domain + `analytics/replay/models.py` (`Simulated*`) + `analytics/paper/models.py` (`Paper*`) | Float-based copies + lossy `to_domain_*` converters |
| `BrokerId` | `domain/enums.py` (`DATALAKE`) vs `domain/ports/broker_id.py` (`MOCK`) | Same name, divergent members |
| Status semantics | `OrderStatus.is_terminal`, `ORDER_STATUS_TRANSITIONS`, `StatusMapperRegistry` | Global registry populated at import time |

---

## 4. End-to-End Execution Flows

### 4.1 Live order spine (strength)

Intended and mostly real:

```
Signal / OrderRequest
  → ExecutionPlanner / OrderPlacer
  → ExecutionService.place_order
  → PlaceOrderUseCase
  → OrderManager.place_order          ← single owner claim
       → OrderValidator + RiskManager.check_order
       → IdempotencyGuard.check_and_reserve
       → submit_fn (gateway.place_order)
  → ORDER_UPDATED / TRADE events on EventBus
  → TradeRecorder → TRADE_APPLIED → PositionManager
```

`gateway.place_order` is reached from submit fns built by `gateway_submit.make_gateway_submit_fn`, session bridge, or `GatewayExecutionProvider`. Risk and idempotency sit on this spine.

**Exception:** `OrderPlacer` can take an `order_command_fn` that bypasses `ExecutionService` / `OrderManager` entirely (`application/trading/order_placer.py`).

### 4.2 Composition / bootstrap (two roots)

**Root A — CLI / API**

```
interface/ui/services/compose.build_runtime(skip_parity_gate=True)  # DEFAULT True
  → BrokerService (lazy gateway init)
  → runtime.factory.build → TradingRuntimeFactory.build_from_broker_service
       → validate_production_config
       → assert_runtime_parity_or_raise  # SKIPPED when skip_parity_gate=True
       → wire TradingOrchestrator + CommandDispatcher
       → optionally asyncio.run(build_infrastructure) for multi-broker
```

**Root B — SDK**

```
tradex.open_session
  → bootstrap_gateway + create_data_adapter + create_execution_provider
  → build_oms_service()          # DIFFERENT OMS constructor than Root A
  → CommandDispatcher (3rd PlaceOrderCommand mapping copy)
```

`PlaceOrderCommand` mapping closures exist in at least three places (`trading_runtime_factory`, two sites in `tradex/session.py`).

### 4.3 Backtest / replay / paper

```
OHLCV DataFrame
  → BacktestEngine.run  [defaults ResearchMode.PURE_SIM → oms_adapter=None]
  → ReplayEngine.run
       per bar: window → FeaturePipeline → StrategyPipeline → Signal
       → pending (NEXT_OPEN) or SignalProcessor → OmsBacktestAdapter | _process_simulated
  → StatisticsEngine
```

`PaperTradingEngine` does **not** wrap `ReplayEngine`. It reimplements the bar loop, session, signal processing, and position closer. Shared pieces: `StrategyPipeline`, `FeaturePipeline`, `OmsBacktestAdapterPort`, `domain.trading_costs`.

### 4.4 Broker connect

```
infrastructure/gateway/factory.bootstrap_gateway
  → _create_transport_gateway (plugin builders from runtime.broker_builders)
  → structural readiness + read-only probe
  → remint once on token rejection
  → BootstrapResult (READY | REAUTH_REQUIRED | FAILED) — refuses dead live gateways
```

Adapters: `DhanWireAdapter` / `UpstoxWireAdapter` behind `domain.ports.broker_adapter.BrokerAdapter`. Import direction for brokers → application/interface is clean (0 matches).

---

## 5. Expected Behavior Contract (as the system claims)

| Dimension | Contract |
|---|---|
| **Inputs** | Market data (live WS / historical OHLCV), strategy signals, operator/API order intents, env/config |
| **Outputs** | Broker orders/fills, positions, equity curves, events on `EventBus`, API/CLI responses |
| **Timing** | Live: fail-closed before actionable; replay/backtest deterministic; parity gate before live boot |
| **State transitions** | Order status via `ORDER_STATUS_TRANSITIONS`; positions via fills + `TRADE_APPLIED`; reconciliation heals drift |
| **Failure modes** | Auth failure → no gateway; risk reject → no submit; idempotent retry → no double order; missed WS → recon heals |

### 5.1 Contract vs code

| Contract item | Enforced? |
|---|---|
| Domain stays inward-only | **Yes** |
| Brokers do not import application/interface | **Yes** |
| Application does not import infrastructure | **No** (9+ direct imports; import-linter false-green) |
| backtest == replay == live P&L | **No** (paper double-slippage, no fill_model, commission/session desync) |
| Parity gate before live boot | **No** (`compose.build_runtime` defaults `skip_parity_gate=True`; also hardcoded in UI/main and tradex) |
| Reconciliation heals | **No** (`ExecutionEngine.apply_mass_status` only builds drift lists; returns without writing OMS) |
| Daily loss = intraday realized | **No** (`TradingContext._feed_daily_pnl` feeds absolute MTM book PnL) |
| Order idempotency survives restart | **No** (in-memory `IdempotencyGuard` / `_orders_by_correlation`) |
| One composition root / OMS ctor | **No** |
| One `normalize_symbol` semantics | **No** (domain keeps `-EQ`; datalake strips suffixes) |
| API does not depend on UI | **No** (`live/portfolio.py`, `api/bootstrap.py` import UI services) |

---

## 6. Metrics (re-baselined 2026-07-17 — GOV-4)

| Metric | Value | Notes |
|---|---|---|
| **Total tests** | 7,885 (`def test_`) | across 968 test files |
| **Architecture tests** | 278 defs | across 66 files in `tests/architecture/` |
| **`src/` total LOC** | 158,910 | all `.py` files under `src/` |
| **Files >650 LOC** | 3 | `depth_feed_base.py` (708), `context.py` (739), `engine.py` (698) |
| **Coverage gate** | ≥80 (brokers ≥85, oms ≥90) | unchanged |
| **CI workflows** | 8 | `ci`, `architecture-enforcement`, `web`, `production_gate`, `dhan-regression`, `mutation_nightly`, `load-test`, `broker_live_certify` |
| **import-linter contracts** | 16 | all passing |
| **God classes** | Decomposed | RiskManager→454, TradingContext→677, UpstoxTokenManager→231 |
| **Plugin entry-points** | `tradex.brokers`, `tradex.exchanges` | both registered |

---

## 7. Gap Analysis (G1–G8)

| Gap | Status | Description |
|---|---|---|
| **G1** | **DONE** | Runtime broker coupling + string branching — removed `_active_name` string branch; added `BrokerId` enum + arch guard |
| **G2** | **DONE** | Shadow `brokers/dhan/*` at repo root — deleted; guard test in place |
| **G3** | **DONE** | Datalake NSE/IST specifics — NSE plugin created; exchange registry with lazy discovery |
| **G4** | **DONE** | Two config systems — `AppConfig` (application) vs `BrokerSettings` (broker) serve different concerns with zero overlap |
| **G5** | **DONE** | Duplicated infrastructure — dead `domain_bus_adapter` removed; `LiveStrategyEngine` removed; MCP servers serve different bounded contexts |
| **G6** | **DONE** | Reconciliation off hot path — `ReconciliationService` emits `RECONCILIATION_DRIFT` events; periodic timer auto-heals |
| **G7** | **DONE** | `getattr` kill-switch fragility — all `getattr` reach-throughs removed; regression guard in place |
| **G8** | **DONE** | Ad-hoc scripts at repo root — 8 scripts deleted; developers run pytest directly |

---

## 8. Cross-Reference

- Prioritized findings (P0–P3): [`PRIORITIZED-AUDIT.md`](PRIORITIZED-AUDIT.md)
- Target architecture + migration: [`TARGET-STATE.md`](TARGET-STATE.md)
- Architecture review & refreshed roadmap: [`REVIEW.md`](REVIEW.md)
- Engineering backlog: [`backlog.md`](backlog.md)
- Current state (detailed): [`CURRENT-STATE.md`](CURRENT-STATE.md)
