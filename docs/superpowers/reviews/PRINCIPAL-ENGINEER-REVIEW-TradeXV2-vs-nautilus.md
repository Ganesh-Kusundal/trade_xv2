# Principal Engineer Review — TradeXV2 vs. nautilus_trader

> **Follow-on:** Full end-to-end specification (Nautilus-mapped) lives in  
> [`docs/architecture/e2e-spec/README.md`](../../architecture/e2e-spec/README.md).  
> This review remains the findings record; the e2e-spec is the implementation contract.

**Scope:** Holistic architecture, end-to-end execution flow, invariants, risk, and a corrected design.
**Lens:** The system trades real money on NSE/IST. Every order/cancel path needs explicit failure modes, a `RiskGate`, and idempotency. Live == replay == backtest (Zero-Parity).
**Method:** graphify orientation + direct source reads on both trees. No code was modified.

---

## 1. System Intent (the contract the system must satisfy)

| Dimension | TradeXV2 (claimed) | nautilus_trader (reference) |
|---|---|---|
| Core purpose | Indian (NSE/IST) F&O + equity trading OS: research, replay, live | Multi-asset, multi-venue Rust-native engine; research→live with **no code change** |
| Parity | `architecture.md §7.1` — "backtest, replay, and live execution share identical logic" | README — "same execution semantics and deterministic time model in both research and live" |
| Source of truth | OMS order book + `PositionManager` (in-memory, event-driven) | Central `Cache` (orders/positions/accounts) owned by `ExecutionEngine` |
| Time model | Injected `Clock`/`TimeService` (domain purity enforced by test) | Injected `Clock` (`LiveClock`/`TestClock`) injected into **every** component |
| Determinism | `FakeClock`/`TestClock` for replay; `parity_gate` boot test | `TestClock.advance_time` drives **all** engines identically |
| Risk | `RiskManager.check_order` (pre-trade) + `DailyPnlResetScheduler` | `RiskEngine` (pre-trade **and** post-trade) with `TradingState` REDUCING/HALTED + `Throttler` |

Both systems *intend* the same thing. The divergence is **how the intent is enforced**: nautilus bakes it into a single engine + single cache + single clock; TradeXV2 expresses it as rules in `architecture.md` and checks them with a boot-time test + multiple parallel abstractions.

**Verdict up front:** The architecture *contract* is sound and well-documented. The *enforcement* has ≥3 systemic gaps that require redesign, not patches: (a) two execution code paths, (b) off-hot-path reconciliation, (c) wall-clock usage inside the broker fill path that breaks the determinism contract the parity gate is supposed to protect.

---

## 2. Current Architecture Map

### 2.1 Layering (honored — verified)
`domain/` imports nothing inward. Grep for `from application|infrastructure|runtime|brokers|interface` in `src/domain` → **zero matches**. The Six-File layering is real and the import-linter gate works. Good.

```
DOMAIN      (pure, Clock-injected)   value_objects.py, order.py, position_manager state machine,
                                     reconciliation_engine.py, state_machine.py
APPLICATION (OMS/risk/orchestrator)  risk_manager.py, order_manager.py, trading_orchestrator.py,
                                     execution/{execution_mode_adapter,simulated_fill}.py
INFRASTRUCTURE                       event_bus/, idempotency/*, time_service, observability
RUNTIME     (composition root)       parity_gate.py, trading_runtime_factory.py, broker_infrastructure.py
BROKERS     (plugins)                paper/, upstox/, dhan/
ANALYTICS   (replay/backtest)        replay/engine.py, backtest/{engine,run_backtest}.py,
                                     oms_backtest_adapter.py
INTERFACE   (API/TUI/CLI/MCP)        fastapi, textual, click
```

### 2.2 Subsystem inventory (counts reveal duplication)
- **Event buses: 8** — `domain/events/bus.py`, `domain/events/null_bus.py`, `infrastructure/event_bus/{event_bus,async_event_bus,factory}.py`, `brokers/runtime/event_bus.py`, `interface/ui/services/event_bus_service.py`, `domain/ports/event_publisher.py`.
- **Idempotency systems: 4** — `brokers/upstox/orders/idempotency.py`, `brokers/common/idempotency.py`, `application/oms/idempotency_guard.py`, `infrastructure/idempotency/{service,file_cache,redis_cache,memory_cache,codec,exceptions}.py`.
- **Reconciliation services: 4+** — `domain/reconciliation_engine.py` (pure compare), `application/oms/reconciliation/{engine,__init__}.py`, `application/oms/reconciliation_service.py`, `brokers/{upstox,dhan}/.../reconciliation.py`.
- **Execution paths: 2** — live (inlined in `ExecutionService`) and `SimulatedOMSAdapter` (replay/paper).

This duplication is the single biggest architectural smell and is the root cause of the highest-risk failure mode (§5.4).

---

## 3. End-to-End Execution Flow (reconstructed, with real data assumptions)

### 3.1 Live place-order (as built)
1. `TradingOrchestrator.on_candidate(event)` reads `{symbol, score}` from `CANDIDATE_GENERATED`.
2. `CandidateEvaluator` fetches features, `StrategyEvaluator` scores → `Signal`.
3. `ExecutionPlanner` gates (confidence, **kill-switch via injected `RiskManagerPort`**, equity resolution).
4. `OrderPlacer` → `OrderManager.place_order(command, submit_fn)`.
5. `OrderManager`: `IdempotencyGuard.check_and_reserve(correlation_id)` → `RiskManager.check_order(order)` (under `threading.RLock`) → **if pass**, `submit_fn` (broker transport) → on result, `TradeRecorder` records trade idempotently on `trade_id`.
6. `TRADE_APPLIED` published → `PositionManager.on_trade_applied` → `apply_trade` → `project_trade` updates avg price / realized PnL, guarded by `StateMachine` for position states.

### 3.2 Replay / backtest place-order (as built)
1. `BacktestEngine.run(df)` → `ReplayEngine.run(df)` bar-by-bar.
2. Strategy emits signal → `OmsBacktestAdapter.open_long/close_long` builds `OmsOrderCommand` (MARKET, INTRADAY).
3. `create_execution_adapter("replay")` → `SimulatedOMSAdapter.place_order` → `make_simulated_submit_fn` **fills synchronously at `apply_slippage(price)`**.
4. `record_simulated_trade` writes a `Trade` with **`timestamp=datetime.now(timezone.utc)`** (see §5.3).

### 3.3 The parity gap (explicit)
The live path is "inlined directly in `ExecutionService`" — stated in the adapter module itself:

```3:4:src/application/execution/execution_mode_adapter.py
Live mode is inlined directly in :class:`ExecutionService` and no longer
needs a dedicated adapter.
```

So there are **two** order-routing implementations. nautilus uses **one** `ExecutionEngine` for both `BacktestNode` and `TradingNode` (`self._kernel.exec_engine` is the same class; only the `ExecutionClient` differs — `BacktestExecClient` vs the live client). TradeXV2 compensates with a boot test:

```16:26:src/runtime/parity_gate.py
def assert_runtime_parity_or_raise() -> None:
    """Run parity verifiers; raise RuntimeError if checks fail.
    Skipped when ``SKIP_PARITY_GATE=1`` (local dev / tests)."""
    if os.getenv("SKIP_PARITY_GATE", "0") == "1":
        logger.debug("parity_gate: skipped (SKIP_PARITY_GATE=1)")
        return
    if os.getenv("PYTEST_CURRENT_TEST"):
        return
```

**Parity is test-gated and skippable, not structure-gated.** If the two inlined paths drift, the gate only catches it when (a) it actually runs and (b) the specific replay test exercises the divergence. A fill-scheduling difference in `ExecutionService` will not be caught by `test_event_replay_determinism.py`.

---

## 4. Invariant Checklist (vs. nautilus)

| # | Invariant | TradeXV2 status | nautilus |
|---|---|---|---|
| 1 | Zero-parity: one execution engine | ❌ two paths, boot-test-gated | ✅ one `ExecutionEngine` |
| 2 | Reconciliation on hot path | ❌ detached `reconciliation_service.py` (G6) | ✅ `reconcile_execution_mass_status` inside engine |
| 3 | Order FSM enforced at entity | ⚠️ `StateMachine` exists but `Order.with_status()` bypasses it | ✅ `fsm.pyx`, illegal transitions rejected |
| 4 | Position FSM enforced | ✅ `PositionManager` uses `StateMachine` (good) | ✅ |
| 5 | Single event bus | ❌ 8 implementations | ✅ one `MessageBus` |
| 6 | Single idempotency authority | ❌ 4 systems | ✅ per-client dedupe |
| 7 | Deterministic time in fill path | ❌ `datetime.now()` in broker fills (§5.3) | ✅ `TestClock` drives all |
| 8 | Real-time submit throttling | ❌ none | ✅ `Throttler` in `RiskEngine` |
| 9 | Post-trade risk monitoring | ⚠️ daily-PnL only; no REDUCING/HALTED state | ✅ `TradingState` |
| 10 | Fail-closed risk on provider fault | ❌ instrument lookup swallowed (§5.2) | ✅ reject |

**Correction to the earlier summary:** `PositionManager` *does* enforce a position state machine (`domain/state_machine.py` `StateMachine` + `POSITION_STATE_TRANSITIONS`, `position_manager.py:92-136`). The earlier claim of an "unguarded enum" was wrong for *positions*. It is only half-wrong: the **`Order` entity's `with_status()` is a plain `replace()` with no transition check**:

```112:113:src/domain/entities/order.py
    def with_status(self, status: OrderStatus) -> Order:
        return replace(self, status=status)
```

`domain/state_machine.py:24` documents that `OrderStatus` transitions *are* meant to go through a `StateMachine` ("`sm.transition_to(OrderStatus.FILLED)` raises `IllegalTransitionError`"), but nothing forces callers (reconnect handlers, paper fill path, broker mappers) through it. So the guardrail is opt-in and therefore effectively absent on the order hot path.

---

## 5. Failure & Risk Points (silent / real-time / unsafe assumptions / implicit)

### 5.1 Reconciliation is off the hot path (G6) — HIGH
`ReconciliationEngine` is pure, correct comparison logic (good design). But it is *fed* by a detached `application/oms/reconciliation_service.py` + per-broker services that run on a timer/loop, separate from the OMS fill path. nautilus reconciles broker truth into the **same cache the engine reads** on every `reconcile_execution_mass_status` call driven by the client lifecycle.

**Silent failure:** Between two periodic reconciliations, if a websocket fill/update is dropped (at-least-once delivery is assumed but not guaranteed across reconnect), local OMS believes a position is open while broker closed it. `RiskManager.check_order` then reads a **phantom position** (`position_manager.get_position`) → phantom concentration/gross exposure → either over-leverage or a blocked trade. No event fires. The desync heals only on the next timer tick.

### 5.2 Provider fault in `check_order` weakens risk — HIGH
Inside the pre-trade hot path, an instrument-resolution failure is caught and **downgraded to a warning**, skipping the tick-alignment check:

```226:246:src/application/oms/_internal/risk_manager.py
            if self._instrument_provider is not None and order.price > 0:
                try:
                    instrument = self._instrument_provider.resolve(
                        order.symbol, order.exchange
                    )
                    ...
                except Exception as exc:
                    logger.warning("tick_check_instrument_lookup_failed", ...)
```

A provider outage now *removes* a safety check instead of failing closed. This is the exact anti-pattern the review rules forbid ("If any step depends on 'it should work', flag it as a bug").

### 5.3 Wall-clock inside the fill path breaks determinism — HIGH (new finding)
Replay/backtest trades are stamped with `datetime.now(timezone.utc)` directly:

```
src/brokers/paper/paper_orders.py:164,181,226,313,330,354  timestamp=datetime.now(timezone.utc)
src/brokers/upstox/mappers/derivatives_mapper.py:185      ts = parse_iso(...) or datetime.now(tz=timezone.utc)
src/brokers/dhan/websocket/_helpers.py:152               "timestamp": datetime.now(timezone.utc)
src/brokers/upstox/orders/order_command_adapter.py:251   timestamp=datetime.now(timezone.utc)
```

The domain `value_objects.py` docstring explicitly forbids this ("This module NEVER calls the wall clock directly… time is obtained only through an injected `Clock`"). But the *fill generation* — the most parity-critical moment (it produces the trade that drives PnL and position projection) — ignores the injected `Clock` and calls the OS clock. Consequences:
- **Replay is not reproducible** if the recorded `datetime.now()` is used for any ordering/sorting/equity-curve indexing. Two replays of the same input can differ if any downstream logic sorts by that timestamp.
- **Live/replay divergence:** live trades get broker timestamps; replay trades get *now()*. Any code comparing fill time to session bounds, daily-PnL rollover, or strategy state will behave differently between modes — directly violating Zero-Parity.

`parity_gate.py` does **not** assert `TimeService` is the clock source for fill generation, so this breach is invisible to the gate.

### 5.4 Split-brain from duplicated buses/idempotency — HIGH
With **8 event buses** and **4 idempotency systems**, the question "which one is authoritative for this event/order?" has no single answer:
- The orchestrator and the fill pipeline may subscribe to **different** bus instances (e.g. `domain/events/bus.py` vs `infrastructure/event_bus/event_bus.py`). A `TRADE_APPLIED` published on one is invisible to a handler on the other → the risk/UI layer watches a stale or empty stream.
- Idempotency dedupe at 2 layers (OMS guard + broker-common) with different keys/backing stores creates a window where one layer passes a duplicate the other rejected, or vice-versa → **double order** or **lost order**.

### 5.5 External scheduler dependency (no self-heal) — MEDIUM
`RiskManager.reset_daily_pnl` only fires because `DailyPnlResetScheduler` runs at 00:00 IST:

```354:365:src/application/oms/_internal/risk_manager.py
    def reset_daily_pnl(self) -> None:
        """...Called by :class:`DailyPnlResetScheduler` at the configured
        rollover hour (default 00:00 IST)..."""
```

If that process dies, `snapshot()` records `_last_reset_at`; but **`check_order` never inspects it**. So a missed reset either blocks all trading next session (daily-loss check sees stale accumulated PnL) or, if it rolls over the boundary incorrectly, under-reports losses. Silent, and money-relevant.

### 5.6 `pure_sim` bypasses the risk gate — MEDIUM
`BacktestEngine(mode=PURE_SIM)` sets `allow_simulate_without_oms=True`. The docstring is honest that these results are "not a live guarantee," but there is **no type-level barrier** preventing a `pure_sim` config from being promoted to a live one. A research number can become a live risk parameter with no structural guard.

### 5.7 No real-time throttling — MEDIUM
nautilus `RiskEngine` has a `Throttler` on submit/modify rates, protecting the broker and the operator from bursts/fat-fingers. TradeXV2 has no equivalent. A reconnect storm or a runaway strategy loop hits broker rate limits or, worse, places a burst of real orders.

---

## 6. Proposed Correct Architecture (nautilus-aligned)

### 6.1 One `ExecutionEngine`
Collapse live + `SimulatedOMSAdapter` into a single `ExecutionEngine` interface. The only thing that differs between modes is the **fill source** (live `submit_fn` vs replay `make_simulated_submit_fn`), selected at composition time — mirroring nautilus's `ExecutionClient` swap. Parity becomes structural; `parity_gate.py` becomes a regression check, not the enforcement mechanism.

### 6.2 Reconciliation inside the engine (kill G6)
Promote `ReconciliationEngine.compare_*` to run on **every** broker mass-status/mass-position refresh, writing directly into the OMS order book + `PositionManager` that `RiskManager` reads. Delete `application/oms/reconciliation_service.py` and the per-broker `reconciliation/service.py` shells — keep only the pure `domain/reconciliation_engine.py` compare logic. This removes the inter-tick desync window.

### 6.3 Enforce the Order FSM at the entity
Make `Order.with_status(new)` route through a `StateMachine[OrderStatus]` (the `state_machine.py` infra already supports it — `domain/state_machine.py:24` shows the intent). Any reconnect/broker-mapper path that sets status must pass the same guard as positions. One-line fix at the entity; removes the half-guard.

### 6.4 Single Clock for fills (fix §5.3)
The fill-construction path must take a `Clock`/`TimeService` (already injected per `architecture.md`), never `datetime.now()`. In replay, that clock is the `FakeClock` advanced by `ReplayEngine`; in live, the `SystemClock`. This restores Zero-Parity and replay reproducibility.

### 6.5 Collapse duplication
- **Event bus:** keep `domain/events/bus.py` (port) + one infra implementation. Repoint all 7 others; delete the rest.
- **Idempotency:** one authority = `application/oms/idempotency_guard.py`. Brokers stop deduping; they only transport. Delete `brokers/*/idempotency.py` and the `infrastructure/idempotency/*` cache zoo (or keep one store behind the guard).

### 6.6 Fail-closed risk
- §5.2: instrument-lookup failure in `check_order` → return `RiskResult(False, ...)`, not `logger.warning`.
- §5.5: self-heal inside `check_order` — if `now() - _last_reset_at >= 24h`, perform the reset before evaluating daily-loss. No external scheduler dependency.
- Add a `TradingState` (ACTIVE/REDUCING/HALTED) so post-trade monitoring can downgrade rather than only kill.

### 6.7 Real-time throttling
Add a `Throttler`-equivalent on order submit/modify rates at the `ExecutionEngine` boundary (defense against bursts + fat-fingers).

---

## 7. Migration Plan (minimal but correct, ordered by risk)

| Step | Change | Files | Risk | Enforces |
|---|---|---|---|---|
| 1 | `Order.with_status` routes through `StateMachine[OrderStatus]` | `domain/entities/order.py`, add `ORDER_STATE_TRANSITIONS` in `domain/types.py` | Low | Inv#3 |
| 2 | Fill path takes injected `Clock`; replace `datetime.now()` in `paper_orders.py`, `derivatives_mapper.py`, `order_command_adapter.py`, `dhan/_helpers.py` | brokers/* | Med | Inv#7, Zero-Parity |
| 3 | `check_order` instrument-lookup `except` → hard `RiskResult(False)` | `risk_manager.py` | Low | Inv#10 |
| 4 | Self-heal daily-PnL reset inside `check_order` (staleness check), keep scheduler as backup | `risk_manager.py` | Low | Inv#5 fix |
| 5 | Move `ReconciliationEngine` invocation into `ExecutionEngine`/`OrderManager` hot path; delete `reconciliation_service.py` + per-broker shells | application/oms, brokers/* | Med | Inv#2, G6 |
| 6 | Unify live + replay behind one `ExecutionEngine` adapter; `pure_sim` becomes a distinct, non-promotable research config type | execution/*, backtest/* | Med | Inv#1 |
| 7 | Collapse to one event bus + one idempotency authority | event_bus/*, idempotency/*, all imports | Med | Inv#5,#6 |
| 8 | Add `Throttler` at execution boundary | execution engine | Low | Inv#8 |

Steps 1–4 are local, low-risk, and close the HIGH silent-failure modes without a redesign. Steps 5–8 are the structural redesign required by the review mandate (≥2 systemic fixes → redesign, not patches).

---

## 8. Answers to the mandated four questions

**Q1. What can go wrong silently?**
- Local OMS position desyncs from broker truth between periodic reconciliations (G6) → phantom open position feeds risk math (§5.1).
- Illegal `Order` status transition via `with_status()` corrupts fill/avg-price math with no error (§4, Inv#3).
- Instrument-provider outage inside `check_order` *removes* the tick-alignment check instead of failing closed (§5.2).
- 8 buses / 4 idempotency layers disagree → a `TRADE_APPLIED` the risk/UI layer never sees, or a double/lost order (§5.4).

**Q2. What will break under real-time conditions?**
- Missed `DailyPnlResetScheduler` silently blocks or mis-sizes all next-session trading (§5.5).
- No submit/modify throttling → broker rate-limit rejection or a burst of real orders on a runaway loop (Inv#8).
- Two execution code paths drift under edge cases the boot parity test doesn't exercise (§3.3).
- `datetime.now()` in fills makes replay timestamps unstable and live/replay behavior diverge on any time-ordered logic (§5.3).

**Q3. What assumptions are unsafe?**
- "The `DailyPnlResetScheduler` always fires." (no self-heal — §5.5)
- "Instrument provider lookup always succeeds." (downgraded, not failed-closed — §5.2)
- "Parity holds because `parity_gate.py` passes." (skippable via `SKIP_PARITY_GATE`/`PYTEST_CURRENT_TEST`; `pure_sim` bypasses OMS — §3.3, §5.6)
- "All subscribers share one bus / one idempotency layer." (8 / 4 exist — §5.4)
- "Fill timestamps come from the injected Clock." (they come from `datetime.now()` — §5.3)

**Q4. Where is behavior implicit instead of explicit?**
- Order lifecycle: guardrail exists (`StateMachine`) but `Order.with_status()` bypasses it — implicit mutation.
- Live vs replay execution: "the same" by convention (two code paths), not enforced by a shared engine.
- Reconciliation trigger/authority: implicit (detached timer service), not the engine.
- Risk degradation on provider fault: implicit (warning log + check skipped), not an explicit deny.
- Fill time source: implicit OS clock, contradicting the documented `Clock` contract.

---

## 9. Summary
The contract and layering are better than most real-money trading codebases I review. The problems are **enforcement-side**: two execution paths, off-hot-path reconciliation, wall-clock fills, duplicated cross-cutting services, and a fail-open risk branch. Per the review mandate (≥2 systemic fixes → redesign), do **not** patch locally. Apply Steps 1–4 now (low-risk, close HIGH silent modes), then execute the Steps 5–8 structural redesign. No code was changed in this review.
