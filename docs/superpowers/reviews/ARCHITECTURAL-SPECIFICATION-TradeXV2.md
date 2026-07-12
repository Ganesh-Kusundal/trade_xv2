# TradeXV2 — Architectural Specification

> **Superseded for E2E work.** Use the full suite at  
> [`docs/architecture/e2e-spec/README.md`](../../architecture/e2e-spec/README.md)  
> (Nautilus-referenced kernel, flows, domains, migration). This file remains as a short sketch.

**Version:** 1.0 (draft, post-Principal-Engineer review)
**Status:** Spec + target-state redesign (supersedes the "as-built" drift noted in the review)
**Scope:** Layers, bounded contexts (domains), event catalog, end-to-end flows (live + replay), contracts, and the invariants that must hold for real-money trading.

> This document specifies BOTH the current contract and the corrected target state. Sections marked **[TARGET]** are the redesign required by the review; sections without it describe the current intended contract. Where the current code violates the contract, the violation is named inline.

---

## 1. System Intent & Non-Negotiable Invariants

TradeXV2 is a real-money Indian (NSE/IST) F&O + equity trading OS with three execution modes — **live**, **paper**, **replay/backtest** — that must share identical order/risk/position semantics (Zero-Parity).

### 1.1 Invariants (must hold, enforceable, failure = halt)
| ID | Invariant | Enforcement |
|---|---|---|
| I1 | **Zero-Parity** — live, paper, replay share one execution engine | [TARGET] single `ExecutionEngine` |
| I2 | **Deterministic time** — every timestamp in fills/orders/events comes from an injected `Clock`, never `datetime.now()` | `domain/primitives/value_objects.py` + [TARGET] fill path |
| I3 | **Domain purity** — `domain/` imports nothing inward | import-linter (CI) |
| I4 | **Single composition root** — only `runtime/` imports concrete brokers | import-linter (CI) |
| I5 | **Risk gate is a port** — pre-trade approval flows through `RiskManagerPort`, never reflection | `domain/ports/risk_manager.py` |
| I6 | **Reconciliation on hot path** — local state heals against broker truth inside the engine | [TARGET] |
| I7 | **Order FSM** — every status change validated by the canonical transition table | [TARGET] `Order.with_status` |
| I8 | **Idempotency single authority** — one dedupe layer for `correlation_id` / `trade_id` | [TARGET] |
| I9 | **Fail-closed risk** — provider faults reject, never skip a check | [TARGET] |
| I10 | **Event bus single substrate** — one publish/subscribe substrate, typed events | [TARGET] |

### 1.2 Trust boundaries
- **Broker boundary:** `brokers/` may depend on `domain` ports only (I3/I5). It MUST NOT import `application.oms` concretes.
- **Composition boundary:** `runtime/` is the ONLY place concrete broker adapters are selected (by `broker_id` enum, never string `_active_name` branching — G1).
- **Real-money boundary:** every place/cancel/modify must pass `RiskManager.check_order` + idempotency + durable ledger before broker transport.

---

## 2. Layered Architecture (as enforced by import-linter)

```
interface/  ──▶ runtime/  ──▶ infrastructure/ + application/ ──▶ domain/
 (API/TUI/CLI/MCP)   (composition    (adapters, event bus,   (entities, ports,
                     root ONLY        idempotency, metrics,    events, value objs,
                     touches          observability, ledger)   FSM, domain services)
                     concretes)
```

| Layer | Tech | Owns |
|---|---|---|
| Domain | Python (stdlib) | Typed model, ports (Protocols), domain events, FSMs, value objects, pure reconciliation compare, indicator math |
| Application | Python | Use-cases: `oms` (risk, order book, positions), `execution` (engine + modes), `trading` (orchestrator), `portfolio`, `strategy_engine`, `streaming`, `data` |
| Infrastructure | Python | Cross-cutting: config, auth, persistence (DuckDB/SQLite/Redis), resilience, event bus, metrics, observability, ledger, time |
| Runtime | Python | Composition root: broker discovery, wiring, `parity_gate` |
| Brokers | Python plugins | Dhan / Upstox / Paper adapters satisfying `BrokerAdapter` |
| Datalake | Python + DuckDB | Ingestion, quality, storage, analytics, research |
| Interface | FastAPI/Textual/Click + React/TS | Presentation over the SDK |

Dependency rule (enforced, rules 1–4): `domain`→∅; `application`→`domain`; `infrastructure`→`domain`+`application` ports; `runtime`→everything (concretes only here); `interface`→`application`+`runtime`, never `brokers` directly.

---

## 3. Bounded Contexts (Domains) & Module Map

### 3.1 `domain/` — the contract layer (pure, Clock-injected)
- **Value objects** (`primitives/value_objects.py`): `Money` (currency-tagged, same-currency-only arithmetic), `Quantity`, `Clock` (protocol). **No `datetime.now()` here** (test-enforced).
- **Entities** (`entities/`): `Order`, `Trade`, `Position`, `MarketDepth`, `QuoteSnapshot`, `Account`.
- **Order lifecycle** (`entities/order_lifecycle.py`): **canonical FSM table** `ORDER_STATUS_TRANSITIONS` (OPEN→{PARTIALLY_FILLED, FILLED, CANCELLED, PARTIALLY_CANCELLED, REJECTED, EXPIRED}; terminal states have empty transition sets).
- **Executions** (`executions/`): `Execution` aggregate owns fills per order; emits `TRADE_APPLIED`.
- **Ports** (`ports/`): `OrderServicePort`, `RiskManagerPort`, `BrokerAdapter`, `ExecutionLedgerPort`, `MarketDataPort`, `EventBusPort`, `DataCatalogPort`, `TimeServicePort`, `MarginProviderPort`, `RiskViewPort`.
- **Events** (`events/`): `EventType` enum, `DomainEvent` (typed, `now()` uses injected `Clock`), `TypedEvents` (`TradeFilledEvent`, `TradeAppliedEvent`, ...).
- **Reconciliation** (`reconciliation_engine.py`): pure compare → `DriftItem` list. No I/O.
- **State machine** (`state_machine.py`): generic `StateMachine[T]` with `can_transition_to` / `transition_to` → `IllegalTransitionError`.
- **Domain services**: `portfolio_projection.project_trade`, `risk.notional.effective_notional`, `scanners`, `indicators`, `candles`, `options` (greeks, chains, strike selection), `instruments` (resolution, metadata).

### 3.2 `application/` — use-cases
- **`oms/`** — the order book spine:
  - `order_manager.py` (`OrderManager`): idempotent `place_order`/`cancel_order`/`modify_order`/`record_trade`/`on_order_update`. Holds order dicts under `threading.RLock`. Delegates to `_lifecycle`, `_trade_recorder`, `idempotency_guard`.
  - `_internal/risk_manager.py` (`RiskManager`): pre-trade checks (kill-switch, loss circuit breaker, tick-alignment, capital, margin, concentration, gross exposure, daily-loss). Internally locked (`RLock`). Delegates to `MarginChecker`, `KillSwitch`, `DailyPnlTracker`, `LossCircuitBreaker`.
  - `position_manager.py` (`PositionManager`): subscribes to `TRADE_APPLIED`; updates positions via `project_trade`; enforces `PositionState` FSM. **Has bounded LRU trade-id dedupe.**
  - `trade_recorder.py`: idempotent trade recording on `trade_id`.
  - `idempotency_guard.py`: **[TARGET] single idempotency authority** (`correlation_id` reserve/check).
  - `reconciliation_service.py` / `reconciliation/engine.py`: **[VIOLATION G6] off hot path** — see §6.
  - `daily_pnl_reset_scheduler.py`: external 00:00 IST reset trigger — **[VIOLATION] no self-heal** (see §7).
- **`execution/`** — `execution_service.py` (live, inlined), `execution_mode_adapter.py` (`SimulatedOMSAdapter` for replay/paper), `simulated_fill.py`, `place_order_use_case.py`, `cancel_order_use_case.py`, `oms_backtest_adapter.py`.
- **`trading/`** — `trading_orchestrator.py`: Scanner→Strategy→OMS facade. Delegates to `CandidateEvaluator`, `ExecutionPlanner`, `OrderPlacer`.
- **`portfolio/`, `strategy_engine/`, `streaming/`, `data/`, `composer/`, `options/`, `scheduling/`, `services/`.

### 3.3 `infrastructure/` — cross-cutting
- `event_bus/` (8 impls today — **[VIOLATION I10]** collapse to one), `idempotency/` (4 systems — **[VIOLATION I8]**), `resilience/` (circuit breaker, retry, rate limiter, backoff), `auth/`, `persistence/` (SQLite ledger/order store, DuckDB pool), `metrics/`, `observability/`, `time/` (`clock.py`, `time_service.py` = `TimeService` + `FakeClock`/`SystemClock`), `security/`.

### 3.4 `runtime/` — composition root
`broker_discovery.py`, `broker_infrastructure.py` (**[VIOLATION G1]** concrete + string branching), `trading_runtime_factory.py`, `parity_gate.py` (boot test — **[TARGET]** becomes regression-only once I1 holds), `composition.py`, `session_infra.py`, `ledger_policy.py`.

### 3.5 `brokers/` — plugins (Paper / Upstox / Dhan)
Each satisfies `BrokerAdapter`: auth, market data, order gateway, portfolio gateway, reconciliation, websocket decoder, instrument loader. **[VIOLATION I2]** fill paths call `datetime.now(timezone.utc)` directly (see §7).

---

## 4. Event Catalog (canonical `EventType`)

### 4.1 Market data
`TICK`, `DEPTH`, `QUOTE`, `QUOTE_UPDATED`, `DEPTH_UPDATED`, `INDEX_QUOTE`, `OPTION_CHAIN`, `BAR_CLOSED`, `SUBSCRIPTION_STARTED`, `SUBSCRIPTION_ENDED`.

### 4.2 Orders & trades (the spine)
`ORDER_REQUESTED` → `ORDER_PLACED` → `ORDER_SUBMITTED` → (`ORDER_UPDATED` | `ORDER_CANCELLED` | `ORDER_REJECTED`) → `TRADE` → `TRADE_FILLED` → `TRADE_APPLIED` → `POSITION_UPDATED` (+ `POSITION_OPENED`/`POSITION_CLOSED`).

### 4.3 Risk & safety
`RISK_APPROVED`, `RISK_REJECTED`, `RISK_LIMIT_BREACHED`, `KILL_SWITCH_TOGGLED`, `DAILY_PNL_RESET`, `DRAWDOWN_LIMIT_HIT`, `CIRCUIT_BREAKER_OPENED`, `CIRCUIT_BREAKER_CLOSED`.

### 4.4 Reconciliation
`RECONCILIATION_DRIFT`, `RECONCILIATION_COMPLETED`.

### 4.5 System / lifecycle
`SERVICE_STARTED/STOPPED/FAILED`, `SYSTEM_STARTED/SYSTEM_SHUTDOWN`, `HEALTH_CHECK_PASSED/FAILED`, `BROKER_CONNECTED/DISCONNECTED`, `TOKEN_REFRESHED/TOKEN_EXPIRED`, `SCAN_STARTED/COMPLETED`, `CANDIDATE_GENERATED`, `SIGNAL_GENERATED`, `SIGNAL_EXECUTED`, `STRATEGY_ACTIVATED/PAUSED/DISABLED`, `EXECUTION_PLAN_BUILT`, `PORTFOLIO_UPDATED`, `METRICS_UPDATED`.

**Event shape:** `DomainEvent(type: EventType, payload: dict, symbol, correlation_id, source, timestamp_from_Clock)`. All events carry a `Clock`-sourced timestamp — never `datetime.now()`.

---

## 5. End-to-End Flows

### 5.1 Live order placement (current contract)

```
[Strategy/Scanner] --CANDIDATE_GENERATED--> [TradingOrchestrator.on_candidate]
        |                                            |
        |                                      CandidateEvaluator (features + strategy)
        |                                            |
        |                                      ExecutionPlanner (confidence, KILL_SWITCH via RiskManagerPort, equity)
        |                                            |
        v                                      OrderPlacer
[OrderManager.place_order(intent, submit_fn)]
   1. IdempotencyGuard.check_and_reserve(correlation_id)        # I8
   2. OrderValidator.build_and_validate(order_id, request)
   3. RiskManager.check_order(order)  [under RLock]             # I5, I9
        - kill-switch (freeze_all) -> REJECT
        - loss circuit breaker -> REJECT
        - tick-alignment (instrument resolve; [VIOLATION] failure swallowed)
        - capital > 0, margin (F&O), concentration, gross, daily-loss
        - on pass: reserve_pending(order, notional)
   4. Lifecycle.submit_to_broker(submit_fn -> BrokerAdapter)    # transport
   5. Lifecycle.record_and_publish -> ORDER_PLACED/ORDER_SUBMITTED, RISK_APPROVED
   6. ExecutionLedger.record_intent / record_outcome           # durable
[Broker websocket] --ORDER_UPDATED--> OrderManager.on_order_update -> upsert_order
[Broker websocket] --TRADE_FILLED--> OrderManager.record_trade (idempotent on trade_id)
        -> TRADE_APPLIED -> PositionManager.on_trade_applied
        -> project_trade -> POSITION_UPDATED (PositionState FSM enforced)
        -> RiskManager.update_daily_pnl(pnl)
```

### 5.2 Replay / backtest (current contract, **[VIOLATION I1/I2]**)
```
[BacktestEngine.run(df)] -> [ReplayEngine.run(df)] bar-by-bar
   for each bar:
     Strategy -> Signal -> [OmsBacktestAdapter.open_long/close_long]
        -> OmsOrderCommand(MARKET, INTRADAY)
        -> ExecutionModeAdapter("replay") -> SimulatedOMSAdapter.place_order
        -> make_simulated_submit_fn (SYNCHRONOUS fill at apply_slippage(price))
        -> record_simulated_trade(timestamp=datetime.now())   # [VIOLATION I2]
        -> TRADE_APPLIED -> PositionManager (same path as live)
```
**Problem:** live = inlined `ExecutionService`; replay = `SimulatedOMSAdapter`. Two code paths. Parity is asserted only by `parity_gate.py` boot test (skippable).

### 5.3 [TARGET] Unified execution (Zero-Parity)
```
        ┌─────────────────── ONE ExecutionEngine ───────────────────┐
        │  IdempotencyGuard → RiskManager.check_order → [Fill Source] │
        │  Fill Source selected at composition:                      │
        │    live   = BrokerAdapter.submit (async, websocket fills)   │
        │    replay = SimulatedFillFn (synchronous, Clock-advanced)   │
        │    paper  = PaperFillFn (synchronous, Clock-advanced)       │
        │  Both feed the SAME order book + PositionManager + Ledger   │
        └────────────────────────────────────────────────────────────┘
```
All three modes share: idempotency authority, risk gate, order FSM, position projection, ledger. Only the **fill source** differs.

---

## 6. Reconciliation Flow (**[VIOLATION G6]** → [TARGET])

### Current (broken)
`ReconciliationEngine.compare_*` is pure and correct, but it is *invoked* by a detached `application/oms/reconciliation_service.py` + per-broker services on a timer. Between ticks, a dropped websocket fill leaves local state desynced from broker truth; `RiskManager.check_order` then reads a **phantom position**. No event fires.

### [TARGET] (hot-path)
```
[Broker mass-status / mass-position refresh]
   -> ExecutionEngine.reconcile(broker_orders, broker_positions, broker_funds)
   -> ReconciliationEngine.compare_orders / compare_positions / compare_funds
   -> for each DriftItem(HIGH/MED/LOW):
        - reconcile order into OrderManager (upsert with FSM-validated status)
        - reconcile position into PositionManager (project_trade, FSM-validated)
        - reconcile funds into RiskManager capital
   -> publish RECONCILIATION_DRIFT / RECONCILIATION_COMPLETED
```
Reconciliation writes into the **same** state the risk manager reads — no inter-tick desync window.

---

## 7. Time & Determinism Contract (**[VIOLATION I2]**)

### Current
- Domain mandates injected `Clock` (`value_objects.py` docstring: "NEVER calls the wall clock"). ✓ in domain.
- **But** fill construction in `brokers/paper/paper_orders.py` (`:164,181,226,313,330,354`), `brokers/upstox/mappers/derivatives_mapper.py` (`:185`), `brokers/upstox/orders/order_command_adapter.py` (`:251`), `brokers/dhan/websocket/_helpers.py` (`:152`) call `datetime.now(timezone.utc)` directly.

### Consequences
1. **Replay not reproducible** — fill timestamps vary per run; any time-ordered logic diverges.
2. **Live/replay divergence** — live fills carry broker timestamps, replay carries `now()`; session-bound/daily-reset/strategy-state logic behaves differently → violates Zero-Parity.
3. `parity_gate.py` does **not** assert `Clock` is the fill-time source → invisible.

### [TARGET]
- `TimeService` (injected) is the **only** timestamp source for order/trade/event construction.
- Replay advances a `FakeClock` per bar; live uses `SystemClock`.
- Dependency: `brokers/*` fill builders take a `Clock` from the wired `TimeServicePort`, never `datetime.now()`.

---

## 8. Risk & Safety Contract

### 8.1 Pre-trade (`RiskManager.check_order`, under `RLock`)
Ordered gates (fail-closed):
1. Kill-switch active (`freeze_all`) → reject **all** actions incl. `exit_all`.
2. Domain `KillSwitch` bridge (optional).
3. Loss circuit breaker (rolling 24h) → reject.
4. Tick-alignment — **[VIOLATION I9]** instrument-lookup failure currently `logger.warning` + skip → **[TARGET]** must reject.
5. Capital > 0.
6. Margin (F&O segments only).
7. Effective notional (never bare qty as rupee notional; MARKET requires LTP/ref).
8. Per-symbol concentration vs `max_position_pct`.
9. Gross exposure vs `max_gross_exposure_pct`.
10. Daily loss vs `max_daily_loss_pct`.
On pass: `reserve_pending(order, notional)`.

### 8.2 Post-trade / monitoring (**[GAP]**)
- Daily-PnL: `DailyPnlTracker` updated by `update_daily_pnl`; reset only by external `DailyPnlResetScheduler` → **[TARGET]** self-heal inside `check_order` via `_last_reset_at` staleness (no external dependency).
- **[TARGET]** add `TradingState` (ACTIVE/REDUCING/HALTED) like nautilus, so post-trade monitoring can downgrade, not only kill.
- **[TARGET]** add real-time submit/modify `Throttler` at the engine boundary (burst/fat-finger protection).

---

## 9. Contracts (Port Signatures)

```python
# domain/ports/order_service.py
class OrderServicePort(Protocol):
    def place(self, intent: OrderIntent) -> OrderResult: ...
    def cancel(self, order_id: str) -> OrderResult: ...
    def modify(self, request: ModifyOrderRequest) -> OrderResult: ...

# domain/ports/risk_manager.py
class RiskManagerPort(Protocol):
    def check_order(self, order) -> RiskResult: ...   # RiskResult(allowed: bool, reason: str|None)
    def is_kill_switch_active(self) -> bool: ...
    def get_status(self) -> dict: ...

# domain/ports/execution_ledger.py
class ExecutionLedgerPort(Protocol):
    def record_intent(self, intent: OrderIntent) -> None: ...
    def record_outcome(self, outcome: SubmissionOutcome) -> None: ...
    def record_fill(self, fill: LedgerFillRecord) -> None: ...
    def outcome_for(self, intent_id: str) -> SubmissionOutcome | None: ...

# domain/ports/event_publisher.py  [TARGET single substrate]
class EventBusPort(Protocol):
    def publish(self, event: DomainEvent) -> None: ...
    def subscribe(self, type: str, handler) -> token: ...
    def unsubscribe(self, token) -> None: ...

# domain/ports/time_service.py
class TimeServicePort(Protocol):
    def now(self) -> datetime: ...   # Clock-sourced, never datetime.now()
```

---

## 10. [TARGET] Corrected Top-Level Design

```
                         ┌──────────────────────────────┐
   Strategy/Scanner ───▶ │   TradingOrchestrator        │
                         │  (Candidate→Plan→Place)      │
                         └──────────────┬───────────────┘
                                        │ OrderServicePort.place(intent)
                                        ▼
                         ┌──────────────────────────────┐
                         │      ExecutionEngine         │  ← ONE, mode-agnostic
                         │  IdempotencyGuard (I8)       │
                         │  RiskManager (I5,I9)         │
                         │  Order FSM (I7)              │
                         │  Fill Source (live/replay/   │
                         │    paper)                    │
                         │  Reconcile-on-refresh (I6)   │
                         └──────┬───────────┬───────────┘
               TRADE_APPLIED    │           │ submit/cancel/modify
                                ▼           ▼
                    ┌────────────────┐  ┌────────────────────┐
                    │PositionManager │  │  BrokerAdapter      │ (runtime-selected)
                    │(Position FSM)  │  │  (Upstox/Dhan/Paper)│
                    └───────┬────────┘  └─────────┬──────────┘
                            │            websocket order/trade updates
                            ▼                     │
                    ┌────────────────┐            ▼
                    │ExecutionLedger │◀─reconcile─┐
                    │(SQLite durable)│            │
                    └────────────────┘  ┌─────────┴──────────┐
                                        │ Single EventBus    │ (I10)
                                        │ RiskManager.update │
                                        │ Reconciliation     │
                                        └────────────────────┘
```
Time: a single injected `TimeService` feeds Order/Position/Trade/Event timestamps everywhere (I2).

---

## 11. Migration Plan (risk-ordered, from review)

| # | Change | Files | Risk | Closes |
|---|---|---|---|---|
| 1 | `Order.with_status` routes through `StateMachine` + `ORDER_STATUS_TRANSITIONS` | `domain/entities/order.py` | Low | I7 |
| 2 | Fill paths take injected `Clock`; replace `datetime.now()` in `paper_orders.py`, `derivatives_mapper.py`, `order_command_adapter.py`, `dhan/_helpers.py` | brokers/* | Med | I2, Zero-Parity |
| 3 | `check_order` instrument-lookup `except` → `RiskResult(False)` | `risk_manager.py` | Low | I9 |
| 4 | Self-heal daily-PnL reset inside `check_order` (staleness on `_last_reset_at`) | `risk_manager.py` | Low | §8.2 |
| 5 | Move `ReconciliationEngine` invocation into engine hot path; delete `reconciliation_service.py` + per-broker shells | application/oms, brokers/* | Med | I6, G6 |
| 6 | Unify live + replay behind one `ExecutionEngine`; `pure_sim` becomes non-promotable research type | execution/*, backtest/* | Med | I1 |
| 7 | Collapse to one event bus + one idempotency authority | event_bus/*, idempotency/* | Med | I8, I10 |
| 8 | Add `TradingState` + `Throttler` at engine boundary | risk, execution | Low | §8.2 |

Steps 1–4 close the HIGH silent-failure modes with low risk and no structural change. Steps 5–8 are the mandated redesign (≥2 systemic fixes → redesign, not patches).

---

## 12. Open Questions / Decisions Needed
1. **Reconciliation cadence** — event-driven (every broker refresh) vs fixed interval? [TARGET] recommends event-driven.
2. **Idempotency store** — in-memory (crash-unsafe) vs SQLite/Redis (durable)? Current `idempotency_guard` is in-memory; recommend durable backing for real-money recovery.
3. **`pure_sim` guard** — should research configs be cryptographically/type separated from live to prevent promotion?
4. **Ledger authority** — `ledger_authority.py` / `ledger_shadow.py` exist; confirm single-writer policy before live.
