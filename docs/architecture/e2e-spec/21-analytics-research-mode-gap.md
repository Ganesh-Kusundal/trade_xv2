# 21 — Analytics Research-Mode Gap (code-grounded)

**Status:** Done — Phase 1–3 (gate tests, cash ledger, capital bind, trade
journal, paper spine, single daily_pnl writer) verified 2026-07-14
**Reference:** Continues from `20-mirror-refactoring-plan.md` (OMS kernel parity — DONE)
**Audience:** Analytics / research / CLI owners
**Rule:** Do **not** re-propose a Nautilus-style "parity kernel" rebuild for this
layer. The OMS/execution kernel is already shared and verified in doc 20. The
remaining work here was plumbing, not architecture.

---

## 0. Headline finding — the kernel already exists

Doc 20 verified that live (`ExecutionEngine.place_order`) and analytics-sim
PARITY mode (`SimulatedOMSAdapter.place_order`) are both thin wrappers over
the identical `TradingContext.order_manager.place_order()` — same
`RiskManager.check_order`, same `IdempotencyGuard`, same order FSM. Only
`submit_fn` differs (`make_simulated_submit_fn` vs live fill). That is the
Nautilus "only the FillSource swaps" pattern, already built.

What was *not* covered by doc 20 is the **research/analytics layer sitting on
top of that kernel**:

| Entry point | Default mode | Opts into OMS kernel? |
|---|---|---|
| `PaperTradingEngine` | Always requires `trading_context`/`oms_adapter` | Yes (raises `TypeError` otherwise) |
| `ReplayEngine` | Requires context unless `allow_simulate_without_oms=True` | Yes when wired |
| `BacktestEngine` | `ResearchMode.PURE_SIM` (bypass) | Only when `mode=PARITY` + context |
| `FastBacktestEngine` | Always direct fills (look-ahead documented) | Never — research scan only |
| API `/backtest` | Explicitly `PURE_SIM`, returns `research_only=True` | No — declared research endpoint |
| `run_backtest.py` / `Analytics.backtest()` (pre-fix) | No PARITY choice | Gap closed — see §2 |

`RiskGateAdapter` (`application/oms/risk_gate_adapter.py`) was **dead code**:
zero production construction sites; only its own unit test built it. Deleted
(plan step 1). Live and sim already route through real `RiskManager` via
`OrderValidator`.

---

## 1. PURE_SIM vs PARITY — intentional, not a bug

```
PURE_SIM (default on BacktestEngine)
  → ReplayEngine(allow_simulate_without_oms=True)
  → fills simulated in FillRecorder
  → NO RiskManager / IdempotencyGuard / order FSM
  → Legitimate: walk-forward / grid-search / multi-symbol CLI scan

PARITY (opt-in)
  → ReplayEngine(trading_context=...) or oms_adapter=...
  → SimulatedOMSAdapter.place_order
  → identical OMS kernel as live
```

**Do not flip `BacktestEngine`'s default.** Fifteen call sites depend on
PURE_SIM; the API router deliberately labels its result `research_only=True`.
Flipping the default would be a breaking plumbing change disguised as a
one-line fix.

---

## 2. What this gap-close shipped (2026-07-14)

1. **Deleted** dead `RiskGateAdapter` + its test; dropped the stale
   `order_manager.py` type-reference comment.
2. **`StrategyRegistry.self_check(golden_bar)`** — fail-loud once at
   `ReplayEngine` / `PaperTradingEngine` construction (BacktestEngine inherits
   via its wrapped ReplayEngine). Does **not** change the per-bar fail-soft
   `except` in `strategy/pipeline.py` (that correctly degrades one bad bar to
   HOLD).
3. **PARITY plumbing at the boundaries that lacked a choice:**
   - `run_backtest.py --parity` (composes a real, broker-free
     `TradingContext` via `create_trading_context`)
   - `Analytics.backtest(trading_context=..., mode=...)`
   - `optimize_grid(..., trading_context=...)` — grid stays PURE_SIM; optional
     context triggers a single PARITY confirmation re-run of the winner
4. **`Analytics.walk_forward(...)`** exposed on the facade (was CLI-only).
5. **Acceptance test**
   `tests/integration/quant/test_analytics_entry_parity.py` —
   asserts `.replay()` / `.backtest(mode=PARITY)` / `.paper()` produce
   identical trade fingerprints + equity (float tolerance) on the same data
   + real `TradingContext`.

---

## 3. Risk state on the PARITY path (Phase 2 + 3 — closed)

Phase 1 documented that PARITY consulted `check_order` without advancing
risk state. Phase 2/3 close the remaining holes:

| Concern | Mechanism |
|---|---|
| Session cash (sizing) | `SimulatedCashLedger` auto-wired when OMS is present (`cash_ledger.py`); fills go through `apply_cash_delta`. Declines with fills — used only for `session.capital`. |
| Risk capital (fixed) | `FixedAccountCapitalProvider(initial_capital)` bound to `RiskManager` — never declines with fills, identical to live `FixedCapital`. Replaces the earlier cash-backed `LedgerCapitalProvider` bind. |
| Dual daily_pnl writers | `TradingContext.set_analytics_daily_pnl_owner(True)` mutes bus `_feed_daily_pnl`; sole writer is `feed_parity_risk_state` |
| Context mutation scope | `TradingContext.analytics_parity_scope(provider)` wraps `run()` in Replay/Paper engines; restores the original capital provider + pnl-owner flag on exit, so a context reused for live is never left with replay state |
| Mid-run sell trade journal | OMS signal sells append `SimulatedTrade` / `PaperTrade` (same math as PositionCloser) |
| Paper spine | PaperTradingEngine uses the same ledger, fixed-capital bind, PnL owner, and `feed_parity_risk_state` inside `analytics_parity_scope` |
| Daily PnL / daily-loss gate | Shared `analytics.replay.parity_risk.feed_parity_risk_state` each bar |
| Gate observability | Concentration rejection + FlipFlop journal/daily-loss + paper FlipFlop capital-bind + restore-after-run tests |

Remaining live-only edges (not claimed as backtest-identical):

- `Throttler` — wall-clock order-rate limit; meaningless under bar replay unless a
  sim clock is injected (out of scope).
- `TradingState` ACTIVE/REDUCING/HALTED — operator-driven live FSM; not
  auto-transitioned from fills on live either, so not driven from replay.
- Loss CB / `DailyPnlTracker.is_stale` use wall-clock (multi-day bar calendars
  do not reset "daily" buckets).
- Risk capital is now **fixed account size**, so near-full-invested sessions no
  longer starve CB/position/gross checks — a fully-invested book is correctly
  sized against the fixed equity base, matching live semantics.

Acceptance coverage:

- Equivalence: `test_analytics_entry_points_parity_equivalence`
- Concentration gate: `test_analytics_entry_points_parity_rejects_risk_blocked_order`
- Trade journal + daily-loss/capital bind: `test_analytics_entry_points_parity_daily_loss_trips`
- Paper journal + capital bind: `test_paper_flipflop_journals_trades_and_binds_capital`

---

## 4. Explicitly out of scope (do not reopen)

- Collapsing `PaperTradingEngine` / `FastBacktestEngine` into `ReplayEngine`
  (Fast exists for O(n) multi-symbol CLI scan; already self-documents as
  non-authoritative with a `production=True` guard).
- Changing `execution_engine.py` / `order_manager.py` / `RiskManager`
  (doc 20 Steps 1–6 DONE).
- Rewriting per-bar strategy exception handling (already correct fail-soft).

---

## 5. How to get a live-parity analytics result

```python
from application.oms.factory import create_trading_context
from analytics.facade import Analytics
from analytics.backtest import ResearchMode
from decimal import Decimal

ctx = create_trading_context(capital_fn=lambda: Decimal("100000"))
result = Analytics().backtest(
    data,
    symbol="RELIANCE",
    trading_context=ctx,
    mode=ResearchMode.PARITY,
)
```

CLI equivalent:

```bash
python -m analytics.backtest.run_backtest --symbol RELIANCE --years 2 --parity
```
