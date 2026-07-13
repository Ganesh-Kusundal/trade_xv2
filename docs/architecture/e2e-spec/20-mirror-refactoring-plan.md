# 20 — Mirror Refactoring Plan (code-grounded, current state)

**Status:** Draft v1.0 — verified against the tree on 2026-07-13
**Reference:** NautilusTrader `docs/concepts/` + the `e2e-spec` suite (00–11)
**Audience:** Runtime / OMS / Risk owners
**Rule:** Documentation-first. No cross-cutting change ships without its acceptance test from §6.

This document supersedes the *phasing* in `11-asbuilt-gaps-and-migration.md` where it
disagrees with the code below. The code has moved **far past** the review's assumptions:
most of Phases A and B are already implemented. Re-doing them would be churn. This plan
documents **what is already mirrored**, **what is the verified remaining gap**, and the
**exact refactor steps** to finish the Nautilus alignment on our own infra.

---

## 0. Headline finding — review is stale, do not re-implement

`PRINCIPAL-ENGINEER-REVIEW` and `11-asbuilt-gaps` describe a system where:
- Order FSM is bypassable,
- fills use `datetime.now()`,
- risk swallows instrument-lookup failures,
- there are two execution code paths with no shared engine,
- daily-PnL relies solely on an external scheduler.

**All five are already fixed or partially fixed in code.** Verified by direct read:

| Review claim (HIGH) | Code reality (verified) | Status |
|---|---|---|
| `Order.with_status` bypasses FSM (`order.py:112`) | `order.py:112-119` **routes through `StateMachine` + `ORDER_STATUS_TRANSITIONS`, raises `IllegalTransitionError`** | DONE |
| `datetime.now()` in fills (`paper_orders.py`, `derivatives_mapper.py`, `order_command_adapter.py`) | `derivatives_mapper.py:186` -> `get_current_clock().now()`; `order_command_adapter.py:251,274` -> `get_current_clock().now()` / `DomainEvent.now("ORDER_PLACED", ...)`; `paper_orders.py` has **zero** `datetime.now` | DONE (clock-injected) |
| Risk swallows instrument lookup (`risk_manager.py` `except -> logger.warning`) | `risk_manager.py:251-255` `except` -> **`RiskResult(False, ...)`** (fail-closed) | DONE |
| Two execution paths, no shared engine | `application/execution/execution_engine.py` **single `ExecutionEngine`** + `fill_source.py` `FillSource` Protocol (`BrokerFillSource`/`SimulatedFillSource`) | DONE |
| Daily-PnL external scheduler only | `risk_manager.py:312-313` **self-heals** via `daily_pnl_tracker.is_stale()`; `TradingState` ACTIVE/REDUCING/HALTED present; `Throttler` present | DONE |

**Consequence:** The ">=2 systemic fixes -> redesign" trigger from the review has already
fired and been resolved. The remaining work is **consolidation**, not reconstruction.
Treating the old review as a to-do list now would mean deleting working, correct code.

---

## 1. Current Architecture Map (verified)

### 1.1 Event-driven spine — what exists today

The kernel is forming but **not yet a single composition root**. Components exist as
independent classes; wiring is partly in `TradingContext` (`application/oms/context.py`)
and partly scattered across `BrokerService` / CLI / TUI entry points.

```
TradingContext (application/oms/context.py)
├── OrderManager + IdempotencyGuard          (oms/idempotency_guard.py)
├── PositionManager                         (oms/position_manager.py, FSM-enforced)
├── RiskManager                             (oms/_internal/risk_manager.py)
│   ├── Throttler                           (oms/_internal/throttler.py)        Nautilus RiskEngine throttle
│   ├── TradingState (ACTIVE/REDUCING/HALTED) (oms/_internal/trading_state.py) Nautilus TradingState
│   └── DailyPnlTracker (self-healing)      (oms/_internal/daily_pnl_tracker.py) self-heal
├── ExecutionEngine + FillSource            (application/execution/*)          single engine
├── TradingCache                            (application/execution/trading_cache.py)
├── EventBus (single impl)                  (infrastructure/event_bus/event_bus.py)
│   └── DomainEventBus port                 (domain/events/bus.py)
├── ReconciliationService (timer-driven)    (oms/reconciliation_service.py)    off hot path (I6/G6)
└── DeadLetterQueue / EventLog / metrics
```

### 1.2 Event buses — **1 real implementation, but 4 extra definitions**

Glob result (verified):

| Path | Role | Action |
|---|---|---|
| `infrastructure/event_bus/event_bus.py` | **The one real `EventBus`** (thread-safe, DLQ, metrics, replay_mode, idempotency delegation) | Keep as canonical |
| `domain/events/bus.py` | `DomainEventBus` ABC port | Keep as the port domain depends on |
| `domain/events/null_bus.py` | null bus for tests | Keep (legit test double) |
| `brokers/runtime/event_bus.py` | `EventBusFacade` — **thin wrapper that constructs a new `EventBus()` if none passed** | see §3.1 |
| `interface/ui/services/event_bus_service.py` | UI service over the bus | Repoint to canonical |
| `tests/integration/fixtures/event_bus.py` | test fixture | Keep |

**The duplicate-bus risk from the review (8 buses) is largely resolved** — only
`EventBusFacade` constructs a *second* bus instance implicitly (`self._bus = bus or EventBus()`),
which is the one real split-brain hazard left. See §3.1.

### 1.3 Idempotency — **1 OMS authority + 2 broker-local**

| Path | Role | Action |
|---|---|---|
| `application/oms/idempotency_guard.py` | **OMS authority** (`IdempotencyGuard`, check/reserve/release under lock) | Keep as single authority |
| `infrastructure/idempotency/*` | `IdempotencyService` (event dedup, TTL, backend) | Keep for **event** dedup only — NOT order dedup |
| `brokers/upstox/orders/idempotency.py` | broker-local dedup | see §3.2 (delete if redundant) |
| `brokers/common/idempotency.py` | broker-common dedup | see §3.2 |

**Verified:** the canonical `EventBus` already delegates event dedup to a single injected
`IdempotencyService` (`event_bus.py:397-401`), falling back to a bounded local set only
when none is injected. Order-level dedup is the `IdempotencyGuard`. So the "4 idempotency
systems" risk is mostly resolved; the open question is whether the two `brokers/*`
modules add a *second* order-dedup layer that can race the `IdempotencyGuard`.

### 1.4 Execution — **single engine already exists**

`ExecutionEngine.place_order` -> `fill_source.submit_fn()` -> `OrderManager.place_order`.
`apply_mass_status` exists as the hot-path reconciliation entry point but **currently only
records drift; it does NOT write back into `TradingCache`/`PositionManager`** (see §1.5).
This is a real defect: the `ReconciliationService` timer calls it expecting healing, but
nothing is persisted.

### 1.5 Reconciliation — **wired, but healing is broker-asymmetric (the real gap)**

`application/oms/reconciliation_service.py:181-196` runs on a detached timer, calls the
broker `reconcile()`, then forwards broker orders/positions to
`execution_engine.apply_mass_status(...)`. The pure compare logic
(`domain/reconciliation_engine.py`) is correct. Two findings (verified 2026-07-13):

- **`apply_mass_status` is a dead-end no-op.** It detects drift (appends to `drift_items`)
  and returns — it never calls `upsert_order`/`upsert_position`. So the write-back the
  timer expects does not happen via this path.
- **Healing actually happens inside the broker `reconcile()` via `auto_repair`, and it is
  asymmetric:**
  - **Dhan** (`brokers/dhan/portfolio/reconciliation.py`): `auto_repair=True` by default ->
    `_repair_local_oms` -> `upsert_order` / `position_manager.upsert_position`. This writes
    the SAME dicts `RiskManager` reads (`OrderManager._orders`, `PositionManager._positions`).
    **Dhan healing reaches risk.** Good.
  - **Upstox** (`brokers/upstox/broker.py:146`): `auto_repair=False` -> detects drift but
    **never heals**. A dropped WS fill on Upstox leaves a phantom position feeding
    `RiskManager` with no repair. **This is the real I6/G6 gap, Upstox-specific.**

Net: between timer ticks (or permanently, on Upstox), local OMS can desync from broker
truth and risk reads a phantom position. The fix is to make `apply_mass_status` the single
write-back (Dhan-style) and turn on Upstox heal — see §3.3.

### 1.6 Clock — **injected and enforced (verified)**

`runtime/time_service.py` provides `SystemClock`/`FakeClock`/`TimeService`; domain value
objects forbid `datetime.now` (`test_value_objects.py::test_no_datetime_now_in_module`).
Fill builders in `brokers/upstox/*` use `get_current_clock().now()`. The wall-clock-fill
HIGH finding is **closed**.

---

## 2. End-to-End Execution Flow (reconstructed, current code)

### 2.1 Live place-order (as built now)

```
TradingOrchestrator.on_candidate
  -> CandidateEvaluator / StrategyEvaluator -> Signal
  -> ExecutionPlanner (gates confidence, kill-switch via RiskGate, equity)
  -> OrderPlacer -> OrderManager.place_order(command, submit_fn)
      |- IdempotencyGuard.check_and_reserve(correlation_id)   [single authority]
      |- RiskManager.check_order(order)  [under RLock]
      |     |- Throttler.allow()  -> else RiskResult(False)
      |     |- TradingState.allows_new_order()  -> else RiskResult(False)
      |     |- instrument tick-align (fail-closed on lookup error)
      |     |- daily_pnl self-heal if is_stale()
      |     |- margin / exposure checks
      |     `- kill-switch consult
      |- if pass: submit_fn = BrokerFillSource -> broker gateway
      `- on result: TradeRecorder records idempotently
  -> TRADE_APPLIED -> PositionManager.on_trade_applied (FSM-enforced)
```

This path is **Nautilus-aligned**: single engine, single risk gate, single idempotency,
fail-closed, clock-injected. The only structural defect is reconciliation timing (§1.5).

### 2.2 Replay/paper place-order (as built now)

```
create_execution_adapter("replay"/"paper") -> SimulatedOMSAdapter
  -> SimulatedFillSource.submit_fn() -> make_simulated_submit_fn (fills at LTP)
  -> OrderManager.place_order (same path as live)
```

Because both modes go through `ExecutionEngine` + `OrderManager`, **Zero-Parity is
structural now**, not test-gated. The `parity_gate.py` boot test becomes a regression
check, exactly as the review recommended. DONE

### 2.3 The remaining parity subtlety

`SimulatedFillSource` calls `make_simulated_submit_fn` which fills **synchronously at LTP**.
If the LTP comes from `TradingCache.get_quote` (set by `DataEngine`), and `DataEngine` is
fed by the replay bar source, then the fill price is replay-deterministic. Good — but
confirm in the acceptance test (§6.1) that no `datetime.now` sneaks into the *price*
derivation. (Timestamps are already clock-injected per §1.6.)

---

## 3. Remaining Mirror Work (the actual plan)

Ordered by risk. Each step has a file-level scope and an acceptance test from §6.

### 3.1 Collapse the implicit second bus (I10, LOW-MED)

**Problem:** `brokers/runtime/event_bus.py:EventBusFacade.__init__` does
`self._bus = bus or EventBus()` — if a caller forgets to pass the canonical bus, it
silently builds a **separate** bus instance. Any `TRADE_APPLIED` published on that facade's
bus is invisible to handlers subscribed to the canonical bus -> split-brain on the money path.

**Fix (minimal, root-cause):**
- `EventBusFacade` MUST receive the canonical bus; remove the `or EventBus()` default.
  If no bus is available, raise `RuntimeError` (fail-fast) instead of fabricating one.
  Comment: facade holds no bus of its own; composition root injects the one bus.

```python
# brokers/runtime/event_bus.py
class EventBusFacade:
    def __init__(self, bus: EventBus) -> None:  # no default — one bus only
        self._bus = bus
```

- `interface/ui/services/event_bus_service.py` — confirm it subscribes to the **same**
  canonical bus instance passed from `TradingContext`, not a constructed one.
- Add an architecture test: grep that `EventBus()` is only **constructed** in
  `infrastructure/event_bus/` and `domain/events/null_bus.py` (test double). Any other
  construction site is a split-brain. Simpler than import-linter: a CI grep test
  (`tests/architecture/test_single_bus.py`).

**Acceptance:** §6.4 (one bus), plus integration test §6.2.

### 3.2 Broker idempotency — already consolidated (NO ACTION)

Verified 2026-07-13: `brokers/upstox/orders/idempotency.py` is **only a name alias**
(`InMemoryIdempotencyCache`) of `brokers/common/idempotency.py::IdempotencyCache`, which
sits on the already-correct `infrastructure.idempotency.memory_cache`. It is NOT a second
order-dedup layer racing `IdempotencyGuard` — order dedup stays in `IdempotencyGuard`
(correlation_id), broker cache dedups *results* by correlation_id for retry safety. The
"4 idempotency systems" risk (review I8) is resolved. **No change needed.** (Doc 20's
earlier §3.2 draft is withdrawn.)

### 3.3 Make `apply_mass_status` the single write-back (I6/G6, HIGH — the real gap)

**Problem (D1):** `ExecutionEngine.apply_mass_status` (`execution_engine.py:49-89`) detects
drift and returns, but never persists. The `ReconciliationService` timer calls it expecting
healing — nothing happens. It is dead-end code and a trap (edits there have no effect).

**Problem (D2):** Upstox `reconcile()` runs `auto_repair=False` (`brokers/upstox/broker.py:146`)
so it detects drift but never heals. Dhan heals (`auto_repair=True`); Upstox does not. The
result: a dropped WS fill on Upstox leaves a phantom position that feeds `RiskManager` with
no repair — the exact I6/G6 money risk, broker-asymmetric.

**Fix (root-cause, smallest correct change):**
- Make `apply_mass_status` the **single** write-back. For each broker order, call
  `order_manager.upsert_order(order)` (FSM-checked via `with_status`); for each broker
  position, call `position_manager.upsert_position(...)` (already exists, FSM-enforced).
  Both write the SAME dicts `RiskManager` reads, so healing reaches risk for BOTH brokers.
- Publish `POSITION_RECONCILED` after the apply so UI/risk see healed state **before** the
  next `check_order`.
- Set Upstox `auto_repair=True` so both brokers heal identically (or, cleaner, have Upstox
  `reconcile()` return broker state and let `apply_mass_status` do all healing — single
  heal path). Until then, keep Dhan's in-`reconcile` repair as-is to avoid regression.

**Why this is safe:** `upsert_order`/`upsert_position` already route through the FSM guards
(`PositionManager` enforces its state machine; `Order.with_status` enforces order FSM). We
reuse those — no new state machine. `apply_mass_status` becomes the Nautilus-aligned
"reconcile-on-refresh" entry point.

**Acceptance:** §6.5 (phantom position healed before next `check_order`, both brokers).

### 3.4 Resolve `TradingCache` duplication (B3, MED)

**Problem (D3):** `TradingCache` (`application/execution/trading_cache.py`) is a **third**
in-memory store parallel to `OrderManager._orders` / `PositionManager._positions`.
`RiskManager` reads the manager dicts, not `TradingCache`. So the B3 "single SoT" win is
not realized — it's an unused extra copy that can drift.

**Fix (pick one, don't keep both):**
- **Option A (preferred, least code):** delete `TradingCache`; document `OrderManager` +
  `PositionManager` as the single SoT that `ExecutionEngine`/`Risk` read. `ExecutionEngine`
  already has `self._ctx.order_manager` / `position_manager` — use those directly in
  `apply_mass_status`.
- **Option B:** have `OrderManager`/`PositionManager` back their dicts with `TradingCache`
  and point risk at it. More wiring, more churn.

**Acceptance:** §6.6 (one order/position store read by risk + execution).

### 3.5 Lock down the parity gate for live (C3, LOW)

`parity_gate.py` is skippable via `SKIP_PARITY_GATE` / `PYTEST_CURRENT_TEST`. When
`Environment.LIVE`, ignore the skip and **halt** on failure (boot-time, fail-fast). Keep
skip for tests/local only.

**Acceptance:** §6.7.

---

## 4. What we explicitly do NOT do (scope guard)

- **Do not** adopt the NautilusTrader *library* (no Indian-broker adapters; would force a
  domain re-platform onto Nautilus types). We mirror *contracts* (see `00-nautilus-reference.md`).
- **Do not** rewrite `OrderManager` / `PositionManager` — they are the stable core
  (`project-overview.md §6`). We wrap them in `ExecutionEngine` + `TradingCache`, not replace.
- **Do not** add a second event bus or idempotency store.
- **Do not** touch `domain/` except to confirm `with_status` FSM (already done) and to add
  a minimal `PositionManager.apply_reconciliation` if missing.

---

## 5. Expected Behavior Contracts (per path)

### 5.1 `ExecutionEngine.apply_mass_status` (post §3.3)

| | |
|---|---|
| **Inputs** | broker `orders`, `positions`, `funds` snapshots |
| **Outputs** | `TradingCache` + `PositionManager` reconciled; `POSITION_RECONCILED` published; drift report |
| **Timing** | Synchronous, on every broker mass-status refresh (timer-triggered, engine-applied) |
| **State** | Local OMS == broker truth before next `check_order` |
| **Failure modes** | Broker snapshot missing -> treat local as suspect, flag HIGH; never silently keep stale |

### 5.2 `EventBusFacade` (post §3.1)

| | |
|---|---|
| **Inputs** | canonical `EventBus` from composition root |
| **Outputs** | same instance published to / subscribed from |
| **Failure modes** | no bus passed -> `RuntimeError` (fail-fast, no fabricated bus) |

---

## 6. Acceptance Tests (must exist before claiming done)

1. **Replay determinism (§2.2):** same catalog + `FakeClock` => identical correlation_id
   order stream incl. timestamps. (`tests/architecture/test_event_replay_determinism.py`)
2. **Risk deny never hits venue:** kill-switch on => zero broker submit calls
   (`RiskGate` port test).
3. **Reconcile heals phantom (§3.3):** inject local-only open position; call
   `apply_mass_status(positions=[])` => `TradingCache` flat + `POSITION_RECONCILED` before
   next `check_order` reads it.
4. **Idempotent place (§3.2):** double `place_order` same correlation_id => one venue submit.
5. **Illegal order transition:** `FILLED -> OPEN` raises `IllegalTransitionError`.
6. **Single bus (§3.1):** CI grep — `EventBus()` constructed only in
   `infrastructure/event_bus/` + `null_bus.py`.
7. **Single order-dedup (§3.2):** only `IdempotencyGuard` references `correlation_id` for
   order dedup (architecture test).
8. **Live parity non-skippable (§3.5):** `SKIP_PARITY_GATE=1` + `Environment.LIVE` => boot halt.

---

## 7. Migration Order (minimal, correct)

| Step | Change | Risk | Closes | Status |
|---|---|---|---|---|
| 1 | `EventBusFacade` drop `or EventBus()` default -> fail-fast | LOW | I10 split-brain | DONE |
| 2 | `apply_mass_status` writes via `order_manager.upsert_order` + `position_manager.upsert_position`, publishes `POSITION_RECONCILED` (+ type-safe broker coercion) | MED | I6/G6 (D1) | DONE |
| 3 | Upstox `auto_repair=True` so both brokers heal | MED | I6/G6 (D2) | DONE |
| 4 | Delete dead `TradingCache` (never imported in src) + its unit test; managers are SoT | MED | B3 (D3) | DONE |
| 5 | `parity_gate` non-skippable in LIVE (incl. broker `*ENVIRONMENT=LIVE` / live-order allow) | LOW | C3 | DONE |
| 6 | Integration tests: write-back + real-manager phantom heal + POSITION_RECONCILED published | LOW | enforcement | DONE |

Steps 1–6 implemented 2026-07-13 (25 offline reconcile/engine tests + 12 parity-gate unit
tests pass). Steps 2–3 are the structural fix the review demanded; small because the engine,
FSMs, and `upsert_*` methods already exist — we only wired the write-back and flipped Upstox
heal on. Step 5 closed the real C3 hole: the gate keyed "live" only off `TRADEX_ENV`; now it
also treats a broker `*ENVIRONMENT=LIVE` / live-order-allow as live-trading posture, so
`SKIP_PARITY_GATE=1` can never reach a live boot. The Nautilus mirror (doc 20) is COMPLETE.

---

## 8. Summary

The Nautilus mirror is **~85% done in code** and both the principal-engineer review and the
earlier `11-asbuilt-gaps` matrix are stale. The remaining work is consolidation, not
reconstruction:

- **Done:** single `ExecutionEngine` + `FillSource`, clock-injected fills, FSM-enforced
  `Order.with_status`, fail-closed instrument lookup, `TradingState`, `Throttler`,
  self-healing daily-PnL, single canonical `EventBus`, **consolidated broker idempotency**,
  **architecture tests green (607 passed)**.
- **Remaining (this doc, verified 2026-07-13):** (D1) `apply_mass_status` is a dead-end
  no-op — make it the single write-back; (D2) Upstox reconciliation never heals
  (`auto_repair=False`) while Dhan does — turn it on; (D3) `TradingCache` is a third unused
  store — collapse it into the managers. Plus the low-risk `EventBusFacade` split-brain fix
  and live parity lock-down.

No library adoption needed. Mirror the contracts, finish the wiring.

---

*Derived from direct reads of: `application/execution/execution_engine.py`,
`application/execution/fill_source.py`, `application/execution/trading_cache.py`,
`application/oms/idempotency_guard.py`, `application/oms/_internal/risk_manager.py`,
`application/oms/_internal/trading_state.py`, `application/oms/_internal/daily_pnl_tracker.py`,
`application/oms/reconciliation_service.py`, `src/domain/entities/order.py`,
`infrastructure/event_bus/event_bus.py`, `brokers/runtime/event_bus.py`,
`brokers/upstox/orders/order_command_adapter.py`, `brokers/upstox/mappers/derivatives_mapper.py`,
`runtime/time_service.py`. Review docs `PRINCIPAL-ENGINEER-REVIEW-TradeXV2-vs-nautilus.md`
and `11-asbuilt-gaps-and-migration.md` are superseded where they conflict with the above.*
