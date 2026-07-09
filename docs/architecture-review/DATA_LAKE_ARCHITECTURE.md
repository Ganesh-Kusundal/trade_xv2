# Data Lake Architecture — TradingOS

**Deliverable 10** (per Charter Phase 9). Status: DESIGN ONLY.

## 1. Current State (Existing Asset — reuse)
- `datalake/` package (115 files, ~18k LOC): `gateway`, `normalize`, `schema`, `option_format`,
  `nse_calendar`, `pit_joins`, `options_analytics_sql`, `options_greeks`, `quality_universe`,
  `research_dataset`, `scan_store`, `scanner_universe`, `sync_options`, `updater`, `validation`,
  `migrations`, `fast_backtest`, `run_backtest`, plus `core/` (`duckdb_utils`) and `adapters/`
  (`analytics_provider`).
- Storage: `market_data/catalog.duckdb` (~100 MB) + Parquet datasets; `.duckdb` + `journal.sqlite`
  + `backtest_results.sqlite` present.
- Already a hybrid: Parquet (immutable partition storage) + DuckDB (analytical engine).

## 2. Target — Canonical Historical Repository
The data lake becomes the **single canonical historical market repository**, reused across
backtest, replay, live warm-up, research, scanner, analytics, and ML. **No duplicate storage
abstractions** (fixes debt D6/D8 — analytics reaches concrete `datalake`; D5 — market_data
scattered).

### 2.1 Dataset taxonomy (one model)
| Dataset | Grain | Notes |
|---|---|---|
| Tick | (instrument, ts) | Raw trades/quotes |
| OHLCV | (instrument, interval, ts) | Bars (1m…1d) |
| Order book / Depth | (instrument, ts, level) | L2 snapshots |
| Options | (option_id, ts) | Greeks, IV, OI |
| Futures | (future_id, ts) | Continuous/contract |
| Corporate actions | (instrument, date) | Splits, dividends |
| Symbol metadata | (instrument_id) | Master, mappings |
| Trading calendars | (exchange, date) | Sessions, holidays |

### 2.2 DuckDB role (analytical)
High-performance analytical queries; vectorized processing; fast scans/aggregations; time-series
joins; research workflows. Source of truth for *queries*; not the immutable store.

### 2.3 Parquet role (storage)
Long-term immutable storage; partitioned datasets (e.g. `exchange=/symbol=/year=/month=`);
efficient replay (columnar, predicate pushdown); exchange-independent.

### 2.4 Canonical identifiers
All datasets keyed by **`InstrumentId`** (domain VO) — one stable key across brokers/exchanges
(reuses `domain.instruments.instrument_id`). Symbol metadata maps broker symbols → `InstrumentId`.

### 2.5 Unified access (single abstraction)
`HistoryManager` (domain service, Target §3) is the only reader; it delegates to a
`datalake` **port** (not concrete classes — fixes D8). Replay is a `DataProvider`/`EventSource`
over the same store, so live and replay share the canonical market model (Charter §8 Success).

## 3. Operations
- **Incremental updates:** append-only partitions; `updater`/`sync_options` evolve to idempotent
  upserts keyed by `(instrument_id, ts)`.
- **Cache strategy:** DuckDB in-process cache for hot symbols; `infrastructure/cache` for derived
  features; invalidation by `ts` + version.
- **Replay performance:** vectorized Parquet reads → domain events in `sequence` order
  (Target §5/§9); deterministic clock from `RuntimeContext`.
- **Scanner queries:** SQL over DuckDB (reuse `options_analytics_sql`, `scanner_universe`,
  `quality_universe`); scanner must not own its own storage.
- **Data quality:** `validation` + `quality_universe` enforced on write; `RECOVERY.md`/parity
  gates flag drift.

## 4. Package mapping (target)
```
infrastructure/
  datalake/        # storage adapter (duckdb/parquet), schema, incremental, replay source
domain/
  market/ history/ # HistoryManager (port consumer), HistoricalSeries VO
```
`analytics` consumes `HistoricalSeries` VOs only — never imports `datalake.gateway`/`research`
concretely (lint-enforced).

## 5. Validation (see TESTING_STRATEGY)
- Data lake validation tests (schema, partition integrity, ID mapping).
- Replay fidelity test: replay event stream == live event stream (byte/order identical).
- Scanner query performance benchmark on canned universe.
