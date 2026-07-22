# ADR-0024: Paper vs replay SignalProcessor hook parity

- **Status:** Accepted
- **Date:** 2026-07-22
- **Deciders:** Architecture review (WS-H)

## Context

REF-5 consolidated paper and replay signal execution into a shared engine
(`analytics.simulation.signal_processor.SignalProcessor`). Mode-specific behavior
is injected via `SignalProcessorHooks` in thin adapters:

- `analytics.paper.signal_processor.PaperSignalProcessor`
- `analytics.replay.signal_processor.SignalProcessor`

Zero-parity applies to the **OMS kernel** (same `OrderManager` / `RiskManager` /
`ExecutionEngine` when an `OmsBacktestAdapter` is wired). Hook differences are
**not** accidental duplication — they encode different simulation fidelity goals:

| Mode | Primary goal |
|------|----------------|
| **Paper** | Live-like session with operator risk limits (position cap, daily loss) and cash-constrained sizing |
| **Replay** | Deterministic historical research; full strategy signal coverage without session-management gates |

This ADR records the four audited hook differences and classifies each as
**INTENTIONAL** (simulation fidelity) or **BUG**. No hook unification is
performed here unless classified as BUG — none were.

## Hook audit

### 1. `entry_gate`

| Aspect | Paper | Replay |
|--------|-------|--------|
| Implementation | `_entry_gate()` — blocks when `position_count >= max_positions`; blocks on daily loss when `via_oms=True` and `max_daily_loss_pct > 0` | `lambda ...: False` — never blocks |
| Return semantics | `True` = **blocked** (shared engine short-circuits) | Always `False` (never blocked) |

**Classification: INTENTIONAL**

**Rationale:**

- **Replay** replays historical bars to measure strategy alpha. Applying
  `max_positions` or `max_daily_loss_pct` would silently drop signals and
  distort backtest statistics — the researcher did not configure those limits for
  the replay run. Risk limits belong in paper (operator session) or live OMS
  paths, not in unconstrained historical replay.
- **Paper** simulates an operator session with explicit capital and risk
  guardrails (`PaperConfig.max_positions`, `max_daily_loss_pct`). The daily-loss
  check runs only on the OMS path (`via_oms=True`) because that path shares the
  production risk kernel; the pure-sim fallback still enforces position count.

### 2. `equity_for_sizing`

| Aspect | Paper | Replay |
|--------|-------|--------|
| Implementation | `lambda session: session.capital` | `lambda session: session.current_equity` |
| With open MTM position | Cash only (buy cost already deducted) | Cash + mark-to-market position value |

**Classification: INTENTIONAL**

**Rationale:**

- **Paper** sizes new entries from **available cash**, matching how a cash account
  funds the next order after prior fills reduce `session.capital`.
- **Replay** sizes from **total mark-to-market equity**, the conventional
  backtest convention when scaling into additional positions while holding open
  exposure. Both sessions compute MTM the same way (`capital + Σ ltp × qty`); the
  hook chooses which numerator the sizing function sees.

When flat, `capital == current_equity` and sizing is identical.

### 3. `position_view`

| Aspect | Paper | Replay |
|--------|-------|--------|
| Implementation | `session._to_paper_position(symbol)` → `PaperPosition` | `session._to_simulated_position(symbol)` → `SimulatedPosition` |

**Classification: INTENTIONAL**

**Rationale:** Both views project the same underlying `SimulationFillPipeline` /
`PortfolioProjector` state. The types differ because downstream bookkeeping
appends mode-specific trade records (`PaperTrade` vs `SimulatedTrade`) with
different metadata fields (e.g. paper tracks `slippage_cost` and `daily_pnl`).

Unifying to one view type would force paper/replay trade models to collapse — out
of scope and not required for OMS zero-parity.

### 4. `slippage_pct` (pure-simulation path hook)

| Aspect | Paper | Replay |
|--------|-------|--------|
| Implementation | `lambda session, bar: self._config.slippage_pct` (fixed) | `lambda session, bar: self._fill_recorder.compute_slippage_pct(bar.volume)` (model-aware) |
| OMS path (`oms_slippage_pct`) | `config.slippage_pct` (fixed) | `config.slippage_pct` (fixed) — **same** |

**Classification: INTENTIONAL**

**Rationale:**

- On the **OMS path**, both modes pass the un-slipped base price and apply
  slippage exactly once inside `OmsBacktestAdapter` (F2a/F2d; see
  `test_oms_slippage_once.py`). `oms_slippage_pct` is identical.
- On the **pure-simulation fallback** (no OMS adapter), replay supports
  `SlippageModel.VOLUME_WEIGHTED` for research realism; paper uses a fixed
  `PaperConfig.slippage_pct` for predictable live-parity sessions. Paper does not
  expose `slippage_model` / `avg_volume` — by design.

## Related differences (documented, not hook-unified)

These are configured alongside hooks but are not one of the four audited hooks:

| Collaborator | Paper | Replay | Classification |
|--------------|-------|--------|----------------|
| `size_for_oms` | `compute_order_quantity` only | `_size_with_affordability` (commission loop) | INTENTIONAL — replay pure-sim/backtest path needs explicit affordability; paper OMS path relies on kernel fill rejection |
| `size_for_simulated` | Commission-aware affordability | Same `_size_with_affordability` | INTENTIONAL — aligned within each mode's equity basis |

## Decision

1. **Do not unify hooks** across paper and replay unless a future audit
   reclassifies a difference as BUG. Current differences are simulation-fidelity
   choices, not zero-parity violations of the OMS kernel.
2. **Regression guard:** `tests/integration/analytics/test_paper_replay_hook_parity.py`
   asserts the documented hook behavior so accidental convergence or divergence
   is caught in CI.
3. **Zero-parity scope reminder:** identical OMS routing, once-only slippage on
   OMS fills, and shared `SignalProcessor` control flow — not identical hook
   lambdas.

## Consequences

- Positive: Explicit contract for operators and researchers; replay stats are not
  silently filtered by paper session limits.
- Negative: Paper and replay position sizes can diverge when open MTM exposure
  exists (cash vs equity sizing) — expected and documented.
- Neutral: Adding a new hook collaborator requires updating both adapters, this
  ADR, and the parity test.

## References

- REF-5 simulation consolidation (`analytics.simulation.signal_processor`)
- ADR-0012 paper-only OMS boundary
- `tests/integration/analytics/test_oms_slippage_once.py` (OMS slippage once)
- `tests/integration/analytics/test_paper_replay_hook_parity.py` (this ADR)
