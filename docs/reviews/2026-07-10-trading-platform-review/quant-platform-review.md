# Quant Platform Review

## Verdict

The research stack is useful for exploratory work, but backtest, replay, paper, and live results cannot currently be treated as economically equivalent. The zero-parity requirement is not met.

## Findings

### Critical: backtests bypass production risk by default

`BacktestEngine` defaults to `ResearchMode.PURE_SIM` and explicitly allows replay without OMS risk (`src/analytics/backtest/engine.py:47-119`). The API creates the engine without demonstrating parity wiring (`src/interface/api/routers/backtest.py:98-105`). A profitable backtest can therefore be generated under rules that would reject live orders.

### Critical: multi-symbol portfolio simulation is not concurrent

Replay runs symbols independently with fresh capital and merges curves afterward (`src/analytics/replay/engine.py:423-455`). Paper processes symbols sequentially and can close positions using the last symbol's price (`src/analytics/paper/engine.py:334-361`). This invalidates exposure, cash, ordering, and cross-asset PnL for portfolio strategies.

### Critical: signal and feature correctness is not enforced

`SwingHighLow` uses centered rolling windows and emits boolean flags, while `BreakoutStrategy` interprets them as numeric swing prices (`src/analytics/pipeline/features.py:253-276`, `src/analytics/strategy/pipeline.py:169-186`). This creates look-ahead bias and semantically invalid breakout levels.

Feature pipeline failures can be swallowed, returning an unenriched frame; replay/paper can then fall back to raw bars (`src/analytics/pipeline/pipeline.py:59-73`, `src/analytics/replay/engine.py:354-359`, `src/analytics/paper/engine.py:192-197`). Missing indicators may become neutral defaults such as RSI 50.

### High: risk reservations are not atomic

Risk checks execute before order insertion and outside the position-book lock (`src/application/oms/order_validator.py:79-127`). Two concurrent signals can both pass against the same exposure. Pending orders must be included in a reservation ledger, not inferred from filled positions.

### High: fill and PnL semantics diverge

The OMS backtest adapter applies slippage when recording a fill (`src/application/execution/oms_backtest_adapter.py:151-160`), while replay shadow state uses the unadjusted price (`src/analytics/replay/engine.py:577-612`). Paper can apply slippage before the adapter (`src/analytics/paper/engine.py:405-424`). This can produce double slippage or inconsistent trade/PnL records.

### High: reconciliation is economically incomplete

Orders compare status but not fill quantity, average fill price, or rejected state. Positions compare quantity but not average price, multiplier, realized PnL, or LTP (`src/domain/reconciliation_engine.py:81-165`). A local position may look reconciled while money values are wrong.

### High: scanner semantics are unsafe

Candidate events omit strong identity fields (`src/analytics/scanner/models.py:215-225`), and orchestrator correlation IDs can collapse to `None:strategy` (`src/application/trading/trading_orchestrator.py:203-207,396-405`). The scanner's `rsi_approx` is a five-day percentage change exposed as `rsi_14` (`src/analytics/views/scanner.py:210-214`, `src/interface/api/routers/scanner.py:131-155`).

## Expected versus actual quant contract

- **Data:** expected point-in-time, validated, timestamped inputs; actual paths can drop, zero, or fallback-fill missing/invalid data.
- **Features:** expected identical bar availability and freshness; actual timing, cache, and fallback behavior differs by mode.
- **Signal:** expected unique strategy/instrument/time identity; actual correlation identity can be absent.
- **Risk:** expected atomic reservations including pending exposure; actual checks can race before insertion.
- **Fill:** expected one authoritative price and cost model; actual OMS, replay shadow, and Paper can differ.
- **Portfolio:** expected chronological multi-asset cash/exposure; actual paths can execute symbol-by-symbol and merge curves.
- **PnL:** expected one source of truth; actual multiple projections and shadows exist.
- **Reconciliation:** expected full economic equality or explicit unknown; actual checks status/quantity incompletely.

## Corrected quant architecture

1. Define a `MarketEvent`/`BarEvent` with exchange time, receipt time, sequence, instrument ID, source, and validity.
2. Make feature computation point-in-time and fail closed on missing required inputs; no neutral substitute for a failed indicator.
3. Emit a unique `SignalDecision` keyed by strategy, instrument, event sequence, and decision version.
4. Convert to an `OrderIntent` through one sizing/risk service with atomic pending reservations.
5. Run all modes through the same intent, execution outcome, fill, and portfolio projector. Backtest/paper only replace event source and fill model.
6. Define intrabar assumptions, next-bar rules, partial fills, fees, slippage, corporate actions, and session boundaries as explicit configuration included in the result artifact.
7. Require walk-forward, out-of-sample, transaction-cost, and portfolio-concurrency validation before a strategy can be promoted.

## Minimum release gate

A strategy result is not promotable unless:

- parity mode is used and OMS/risk wiring is present;
- data provenance and point-in-time checks pass;
- every trade has a deterministic identity and reproducible event trace;
- multi-symbol capital/exposure is simulated chronologically;
- fill/PnL results reconcile to the same ledger used by paper/live;
- missing data, feature failure, and broker uncertainty fail the run rather than silently improving it.
