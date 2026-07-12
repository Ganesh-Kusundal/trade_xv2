# Market Data Domain Objects — Catalog and Ownership

**Version:** 1.0 (ADR-020)  
**Implementation:** `src/domain/candles/`, `src/domain/entities/market.py`

This document is the **shared reference** for OHLCV bar and live tick types. Read with [OBJECT_MODEL.md](./OBJECT_MODEL.md), [GLOSSARY.md](./GLOSSARY.md), [FLOWS.md](./FLOWS.md) §5, and [adrs/adr-020-market-data-domain-ssot.md](./adrs/adr-020-market-data-domain-ssot.md).

---

## Ownership map

| Layer | Owns | Must not own |
|-------|------|--------------|
| **Domain** | Meaning: `HistoricalBar`, `HistoricalSeries`, `MarketTick`, provenance | pandas, HTTP wire shapes |
| **Application** | Fetch intent (`HistoricalQuery`), merge, live aggregation | Parallel OHLCV dataclasses |
| **Brokers / Datalake** | Wire/storage encoding (DataFrame, JSON) | Domain bar definitions |
| **Interface (API)** | Pydantic `Candle` wire schema | OHLCV business logic |
| **Analytics** | Vectorized OHLCV DataFrame **working set** | Alternate in-process bar type |

---

## Domain SSOT (single source of truth)

| Object | Module | Purpose |
|--------|--------|---------|
| `InstrumentRef` | `domain.candles.historical` | `symbol` + `exchange` on bars |
| `HistoricalBar` | `domain.candles.historical` | One OHLCV bar: Decimal OHLC, int volume/OI, UTC `event_time`, `DataProvenance` |
| `HistoricalSeries` | `domain.candles.historical` | Ordered bars + `DateRange` coverage + gaps + optional merge manifest |
| `BarLabelConvention` | `domain.candles.historical` | LEFT / RIGHT / CENTER timestamp semantics |
| `MarketTick` | `domain.entities.market` | One live tick (LTP, volume, provenance) |
| `DataProvenance` | `domain.provenance` | Lineage on every normalized market artifact |

### HistoricalBar factories (ingress)

| Factory | Source | Timezone rule |
|---------|--------|---------------|
| `from_broker_df` (via `HistoricalSeries`) | Broker-normalized DataFrame | UTC-aware; naive → UTC |
| `from_datalake_df` | Parquet / lake DataFrame | Naive **IST** → UTC |
| `from_live_bucket` | Live tick aggregator | UTC bucket boundaries |
| `from_replay` | Replay / paper row | UTC; alias fields `.symbol`, `.timestamp` |

### HistoricalSeries egress (export only)

| Method | Consumer |
|--------|----------|
| `to_dataframe()` | Analytics `FeaturePipeline`, CSV/JSON export |
| `api_candle_from_bar` / `series_to_api_candles` | REST API |

---

## Boundary types (adapters — not domain)

| Type | Location | Rule |
|------|----------|------|
| API `Candle` | `interface.api.schemas` | Wire only (`t/o/h/l/c/v/oi` floats); built only via `candle_mapper` |
| Datalake parquet row | `datalake.core.schema` | Storage SSOT; naive IST timestamps |
| Analytics OHLCV DataFrame | `analytics.core.models` | Working set; columns from `normalize_ohlcv` / `series.to_dataframe()` |

---

## Compatibility aliases (not new types)

| Alias | Resolves to |
|-------|-------------|
| `analytics.replay.models.Bar` | `HistoricalBar` |
| `application.streaming.candle_aggregator.Candle` | `HistoricalBar` |

New code must import `HistoricalBar` / `HistoricalSeries` by canonical name.

---

## Forbidden

- `HistoricalCandle` or any second OHLCV class under `src/domain/`
- `class Bar` / `class Candle` outside `interface.api.schemas.Candle`
- Router-local inline `Candle(...)` construction from raw DataFrame rows
- NaN OHLC coerced to `0.0` at trust boundaries
- Treating naive lake timestamps as UTC without `from_datalake_df`

---

## HTTP candle routes (must converge)

| Route | Ingress | Egress |
|-------|---------|--------|
| `GET /market/candles` | `DataLakeGateway` → `from_datalake_df` | `series_to_api_candles` |
| `GET /market/live/candles` | `MarketDataComposer` → `HistoricalSeries` | `series_to_api_candles` |
| `GET /live/candles` | `Instrument.history()` → `HistoricalSeries` | `series_to_api_candles` |
