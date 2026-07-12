# ADR-020: Market Data Domain SSOT (Bars and Ticks)

**Status:** Accepted  
**Date:** 2026-07-11  
**Supersedes:** ad-hoc `HistoricalCandle`, parallel DataFrame→bar mappers

## Context

Market OHLCV data entered the codebase through multiple shapes: `HistoricalBar`, `HistoricalCandle`, aggregator `Candle`, replay `Bar`, API float `Candle`, and raw pandas DataFrames. HTTP routes used different conversion paths; datalake storage uses naive IST while domain bars use UTC. This caused silent timestamp shifts, NaN→0 masking, and zero-parity violations between backtest, lake, and live endpoints.

## Decision

1. **In-process SSOT:** `HistoricalBar`, `HistoricalSeries`, and `MarketTick` are the only domain market facts.
2. **Ingress family:** All external OHLCV enters via:
   - `HistoricalSeries.from_broker_df` — broker wire / coordinator DataFrames
   - `HistoricalSeries.from_datalake_df` — parquet lake (IST naive → UTC)
   - `HistoricalBar.from_live_bucket` — live tick aggregation
   - `HistoricalBar.from_replay` — replay / paper simulation
3. **Egress family:** REST candles built only via `api_candle_from_bar` and `series_to_api_candles` in `interface.api.candle_mapper`.
4. **DataFrame rule:** pandas OHLCV is **storage or analytics working set only**, never a domain return type for history APIs.
5. **Provenance:** Every `HistoricalBar` carries `DataProvenance`; lake bars use `broker_id="datalake"`.
6. **Fail loud:** Missing timestamp columns, NaN OHLC, or unsupported timeframe → error; no zero-fill at boundaries.
7. **Forbidden:** `HistoricalCandle` and new parallel `Bar`/`Candle` domain classes.

## Consequences

- Upstox mappers emit `HistoricalBar` instead of `HistoricalCandle`.
- `dataframe_to_historical_bars` and `_df_to_historical_series` delegate to `from_broker_df`.
- All three candle HTTP routes share `series_to_api_candles`.
- Architecture tests ban duplicate OHLCV class definitions.
- `docs/architecture/MARKET_DATA_OBJECTS.md` is the catalog for onboarding.

## References

- [MARKET_DATA_OBJECTS.md](../MARKET_DATA_OBJECTS.md)
- [OBJECT_MODEL.md](../OBJECT_MODEL.md) — Market data section
- [FLOWS.md](../FLOWS.md) §5
- ADR-016 (market data event bus / tick parity)
