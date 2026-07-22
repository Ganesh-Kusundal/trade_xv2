# ADR-0023: Contract-centric multi-asset historical data

- **Status:** Accepted
- **Date:** 2026-07-22
- **Deciders:** Architecture review

## Context

Historical data is split across three incompatible pipelines:

1. **Equities/indices** — federated `HistoricalDataCoordinator` + Dhan/Upstox router.
2. **Options** — Dhan-only rolling ATM±N sync (`OptionsHistoricalCoordinator`).
3. **Futures** — live chain discovery only; no lake ingestion.

Rolling option partitions (`expiry_kind`, `expiry_code`) cannot represent exact expired
contracts. Capability flags overstate expired support (`supports_expired_options_history`
passes validation via generic `history()`). Provenance is computed at fetch time but not
persisted. MCX has broker coverage but no exchange calendar plugin.

## Decision

1. **Canonical identity:** Every derivative bar is keyed by `InstrumentId`
   (`exchange:underlying:expiry:strike:right`). Rolling ATM±N views are derived, never
   canonical storage.
2. **Separate endpoints, shared lifecycle:** Public API exposes
   `/historical/equities`, `/historical/options`, `/historical/futures`. All share one
   internal resolve → route → quota → fetch → normalize → validate → merge → persist
   pipeline with identical provenance envelopes.
3. **Truthful routing:** Router eligibility is lane-specific:
   `(asset_kind, exchange, contract_state, timeframe, lookback_days)`. Dhan rolling
   expired options is NFO index only. Upstox exact expired contracts require Plus
   entitlement preflight. Dhan never serves expired intraday futures.
4. **Rate-limit authority:** `brokers/common/rate_limit_config.py` is the single source;
   capability snapshots import from it.
5. **Contract-centric lake layout:**
   - `contracts/options/candles/exchange={}/underlying={}/expiry={}/timeframe={}/`
   - `contracts/futures/candles/exchange={}/underlying={}/expiry={}/timeframe={}/`
   Legacy `options/candles/` (rolling) remains read-only until cutover parity passes.
6. **Fail-closed default:** Partial/degraded fetches do not advance watermarks unless
   `allow_partial=true`. Provenance + merge manifest persisted with each write.
7. **MCX calendar:** Add `plugins/exchanges/mcx` before MCX gap validation.

## Broker lane truth

| Lane | Dhan | Upstox |
|------|------|--------|
| NSE/MCX active equity/index/fut/opt OHLCV | Yes (via `history()`) | Yes (V3 historical) |
| NFO index rolling expired options | Yes (`/charts/rollingoption`) | No |
| Exact expired opt/fut (any exchange) | No | Yes (Plus plan) |
| Expired intraday futures | No | Per entitlement |

Single-source lanes return explicit provenance; federation never implies a fallback that
cannot serve the contract.

## Consequences

- Positive: One auditable path for all asset classes; expired contracts addressable;
  research/backtest parity with live fetch semantics.
- Negative: Re-fetch required for contract-centric history; rolling lake not converted
  in place.
- Migration: Shadow-write contract partitions; parity gate before reader cutover.

## Validation

- Architecture tests: datalake does not import application; no Trade_J sync paths.
- Integration matrix: NSE + MCX active/expired lanes with real broker credentials.
- Benchmark pass: zero quota violations, zero unresolved gaps under internal rate profiles.
