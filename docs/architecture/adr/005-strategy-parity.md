# ADR-005: Strategy Pipeline Parity Across All Modes

## Status

Accepted

## Context

Trading strategies must behave identically whether running in Scanner, Backtest, Replay, Paper, or Live mode. Historical inconsistencies between modes led to strategies that worked in backtest but failed in live, or produced different signals in paper vs. live due to divergent data paths.

## Decision

The **same strategy pipeline** is used across all five modes:

1. **Scanner** — real-time market scanning with live data
2. **Backtest** — historical data replay through the same indicator/strategy engine
3. **Replay** — market replay with simulated time progression
4. **Paper** — simulated execution against live data feed
5. **Live** — real execution against live market data

The pipeline consists of:
- Market data normalization (domain `HistoricalBar` / `Tick` types)
- Indicator computation (domain indicators: RSI, ATR, VWAP, MACD)
- Strategy signal generation (domain strategy protocols)
- Order intent creation (domain `OrderIntent`)
- Execution dispatch (via CQRS `CommandDispatcher` — ADR-012)

Mode-specific behavior is confined to:
- Data source adapter (live feed vs. historical Parquet vs. paper feed)
- Execution adapter (live broker vs. paper broker vs. no-op)
- Time source (market clock vs. replay clock)

### Severity vocabulary

The reconciliation engine uses a canonical severity vocabulary: `"HIGH"`, `"MEDIUM"`, `"LOW"` (see `domain/reconciliation_engine.py`).

## Consequences

**Positive:**
- A bug found in backtest is reproducible in paper/live with the same strategy code.
- Strategy development loop is faster (backtest → paper → live without code changes).
- Parity testing can validate mode equivalence systematically.

**Negative:**
- Slight overhead from using the full pipeline in modes that don't need all components.
- Mode-specific adapters must be kept thin and well-tested.

## Enforcement

- `tests/architecture/test_shadow_parity_gate.py` — shadow parity between modes
- `tests/architecture/test_flow_contracts.py` — flow contract validation
- `tests/architecture/test_domain_bar_types.py` — OHLCV bar shapes use HistoricalBar as SSOT
