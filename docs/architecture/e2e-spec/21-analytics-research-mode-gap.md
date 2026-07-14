# 21 — Analytics Research-Mode Gap (code-grounded)

**Status:** Done — verified against the tree on 2026-07-14
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

## 3. Explicitly out of scope (do not reopen)

- Collapsing `PaperTradingEngine` / `FastBacktestEngine` into `ReplayEngine`
  (Fast exists for O(n) multi-symbol CLI scan; already self-documents as
  non-authoritative with a `production=True` guard).
- Changing `execution_engine.py` / `order_manager.py` / `RiskManager`
  (doc 20 Steps 1–6 DONE).
- Rewriting per-bar strategy exception handling (already correct fail-soft).

---

## 4. How to get a live-parity analytics result

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
