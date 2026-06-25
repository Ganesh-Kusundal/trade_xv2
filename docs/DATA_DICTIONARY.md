# Trade_XV2 Data Dictionary

## Core Schemas

### OHLCV Candle (equities/indices)

Stored as Hive-partitioned Parquet under `market_data/equities/candles/timeframe={timeframe}/symbol={symbol}/data.parquet`.
Partitioned by `timeframe` (1m, 5m, 15m, 30m, 1h, 1d, 1w) and `symbol`.

| Field | Type | Timezone | Nullable | Description | Example |
|-------|------|----------|----------|-------------|---------|
| `timestamp` | `timestamp(ns)` | IST (naive) | No | Bar open time in Asia/Kolkata | `2024-01-15 09:15:00` |
| `symbol` | `string` | — | No | NSE symbol, uppercased, exchange suffixes stripped | `RELIANCE` |
| `exchange` | `string` | — | No | Exchange code | `NSE`, `BSE`, `NFO` |
| `open` | `float64` | — | No | Opening price in rupees | `2510.50` |
| `high` | `float64` | — | No | Highest price in rupees | `2535.00` |
| `low` | `float64` | — | No | Lowest price in rupees | `2505.25` |
| `close` | `float64` | — | No | Closing price in rupees | `2522.75` |
| `volume` | `int64` | — | No | Number of shares traded | `1250000` |
| `oi` | `int64` | — | No | Open interest (0 for equities) | `0` |
| `vwap` | `float64` | — | Yes | Volume-weighted average price | `2518.30` |
| `trade_count` | `int64` | — | Yes | Number of trades in bar | `850` |

PyArrow schema defined in `datalake/schema.py:ARROW_SCHEMA`.
`vwap` and `trade_count` are optional columns defined in `OPTIONAL_COLUMNS` but not always present in migrated data.

### Option Candle (options)

Stored as Hive-partitioned Parquet under `market_data/options/candles/underlying={underlying}/{expiry_kind}/{expiry_code}/data.parquet`.
Partitioned by `underlying`, `expiry_kind`, `expiry_code`.

| Field | Type | Timezone | Nullable | Description | Example |
|-------|------|----------|----------|-------------|---------|
| `timestamp` | `timestamp(ns)` | IST (naive) | No | Bar open time in Asia/Kolkata | `2024-01-15 09:15:00` |
| `symbol` | `string` | — | No | Canonical option symbol: `{underlying}_{expiry_kind}_{code}_{strike_offset}_{type}` | `NIFTY_WEEK_1_-2_CALL` |
| `underlying` | `string` | — | No | Underlying index or stock | `NIFTY`, `BANKNIFTY` |
| `exchange` | `string` | — | No | Exchange code | `NSE` |
| `open` | `float64` | — | No | Opening price in rupees | `150.25` |
| `high` | `float64` | — | No | Highest price in rupees | `155.00` |
| `low` | `float64` | — | No | Lowest price in rupees | `148.50` |
| `close` | `float64` | — | No | Closing price in rupees | `152.75` |
| `volume` | `int64` | — | No | Number of contracts traded | `25000` |
| `oi` | `int64` | — | No | Open interest in contracts | `150000` |
| `iv` | `float64` | — | Yes | Implied volatility | `18.50` |
| `spot` | `float64` | — | No | Underlying spot price in rupees | `22150.00` |
| `strike` | `float64` | — | No | Strike price in rupees | `22200.00` |
| `strike_offset` | `int64` | — | No | Strike offset from ATM (0 = ATM, -2 = 2 strikes below, etc.) | `-2` |
| `option_type` | `string` | — | No | Option type | `CALL`, `PUT` |
| `expiry_kind` | `string` | — | No | Expiry kind | `WEEK`, `MONTH` |
| `expiry_code` | `int64` | — | No | Sequential expiry code (1, 2, ...) | `1` |
| `interval_min` | `int64` | — | No | Bar interval in minutes | `1` |
| `expiry_date` | `string` | — | Yes | Actual expiry date (ISO format) | `2024-01-18` |

Canonical columns defined in `datalake/option_format.py:CANONICAL_COLUMNS`.

---

## DuckDB Catalog Tables

The catalog database lives at `market_data/catalog.duckdb`. All timestamps are stored as naive IST.

### `symbols`

Registered symbol metadata. Created in `datalake/catalog.py:_init_schema`.

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| `symbol` | `VARCHAR` | No | Primary key. Normalized symbol name | `RELIANCE` |
| `exchange` | `VARCHAR` | Yes | Exchange code (default NSE) | `NSE` |
| `instrument_type` | `VARCHAR` | Yes | Instrument type | `EQUITY` |
| `sector` | `VARCHAR` | Yes | Sector classification | `Oil & Gas` |
| `isin` | `VARCHAR` | Yes | ISIN identifier | `INE002A01018` |
| `lot_size` | `INTEGER` | Yes | Lot size (default 1) | `1` |
| `tick_size` | `DOUBLE` | Yes | Minimum price tick | `0.05` |
| `first_date` | `DATE` | Yes | Earliest available trading date | `2020-01-01` |
| `last_date` | `DATE` | Yes | Latest available trading date | `2024-06-25` |
| `total_rows` | `BIGINT` | Yes | Total number of candle rows | `1000000` |
| `timeframe` | `VARCHAR` | Yes | Candle timeframe (default 1m) | `1m` |
| `parquet_path` | `VARCHAR` | Yes | Relative path to Parquet file | `market_data/equities/candles/timeframe=1m/symbol=RELIANCE/data.parquet` |
| `created_at` | `TIMESTAMP` | Yes | Row creation timestamp | `2024-01-15 09:16:05` |
| `updated_at` | `TIMESTAMP` | Yes | Last update timestamp | `2024-06-25 09:30:00` |

### `data_quality`

Data quality metrics per symbol per check. Created in `datalake/catalog.py:_init_schema`.

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| `symbol` | `VARCHAR` | No | Symbol name (PK) | `RELIANCE` |
| `check_date` | `DATE` | No | Date of quality check (PK) | `2024-06-25` |
| `timeframe` | `VARCHAR` | No | Candle timeframe (PK, default 1m) | `1m` |
| `total_rows` | `BIGINT` | Yes | Total rows scanned | `1000000` |
| `missing_candles` | `INTEGER` | Yes | Count of expected-missing candles | `5` |
| `duplicate_candles` | `INTEGER` | Yes | Count of duplicate timestamp rows | `0` |
| `gap_days` | `INTEGER` | Yes | Number of gap days | `2` |
| `min_date` | `DATE` | Yes | Earliest date in data | `2020-01-01` |
| `max_date` | `DATE` | Yes | Latest date in data | `2024-06-25` |
| `completeness_pct` | `DOUBLE` | Yes | Completeness percentage | `99.85` |
| `status` | `VARCHAR` | Yes | Quality status | `OK`, `WARNING`, `ERROR` |
| `details` | `VARCHAR` | Yes | Additional details / error message | `Missing 5 candles on 2024-06-20` |
| `created_at` | `TIMESTAMP` | Yes | Row creation timestamp | `2024-06-25 09:30:00` |

**PK**: `(symbol, check_date, timeframe)`.

### `download_jobs`

Historical download job tracking. Created in `datalake/catalog.py:_init_schema`.

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| `job_id` | `INTEGER` | No | Auto-increment job ID (PK) | `42` |
| `universe` | `VARCHAR` | Yes | Universe being downloaded | `NIFTY500` |
| `timeframe` | `VARCHAR` | Yes | Candle timeframe | `1m` |
| `symbols_total` | `INTEGER` | Yes | Total symbols to download | `500` |
| `symbols_completed` | `INTEGER` | Yes | Symbols completed successfully | `498` |
| `symbols_failed` | `INTEGER` | Yes | Symbols that failed | `2` |
| `status` | `VARCHAR` | Yes | Job status | `PENDING`, `RUNNING`, `COMPLETED`, `FAILED` |
| `started_at` | `TIMESTAMP` | Yes | Job start time | `2024-06-25 08:00:00` |
| `completed_at` | `TIMESTAMP` | Yes | Job completion time | `2024-06-25 08:45:30` |
| `error_message` | `VARCHAR` | Yes | Error details and stacktrace | `Connection timeout for symbol XYZ` |

### `universe_symbols`

Universe-to-symbol membership mapping. Created via migration v1 (`datalake/migrations.py`).

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| `universe` | `VARCHAR` | No | Universe name (PK) | `NIFTY50` |
| `symbol` | `VARCHAR` | No | Symbol (PK) | `RELIANCE` |

**PK**: `(universe, symbol)`.

### `scan_results`

Scanner result snapshots. Created in `datalake/scan_store.py:ensure_scan_table`.

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| `scan_id` | `VARCHAR` | No | Unique scan identifier (PK) | `scan_20240625_093000_momentum_a1b2c3d4` |
| `scanner` | `VARCHAR` | No | Scanner strategy name | `momentum`, `breakout`, `volume` |
| `symbol` | `VARCHAR` | No | Scanned symbol (PK) | `RELIANCE` |
| `score` | `DOUBLE` | No | Scanner score (0-100) | `85.5` |
| `reasons` | `VARCHAR` | Yes | JSON array of scan reasons | `["momentum","volume_spike"]` |
| `universe_size` | `INTEGER` | No | Size of universe scanned | `500` |
| `scanned_at` | `TIMESTAMP` | No | UTC timestamp of scan | `2024-06-25 09:30:00.123` |
| `metadata` | `VARCHAR` | Yes | JSON metadata blob | `{"market_regime":"bullish"}` |

**PK**: `(scan_id, symbol)`.

### `schema_migrations`

Internal schema version tracking. Created in `datalake/migrations.py`.

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| `version` | `INTEGER` | No | Schema version (PK) | `1` |
| `applied_at` | `TIMESTAMP` | Yes | When migration was applied | `2024-06-25 08:00:00` |

---

## Materialized Analytics Tables

Materialized via `ViewManager.materialize()` and stored as versioned Parquet under `analytics_cache/versions/{table_name}/`.
Registered as DuckDB tables via `ViewManager.register_materialized()`. See `analytics/views/manager.py`.

### `m_intraday`

Current trading day's 1m candles (~187K rows). Source: `v_candles_1m`.

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | `timestamp` | Bar open time |
| `symbol` | `VARCHAR` | Symbol |
| `open` | `DOUBLE` | Opening price |
| `high` | `DOUBLE` | Highest price |
| `low` | `DOUBLE` | Lowest price |
| `close` | `DOUBLE` | Closing price |
| `volume` | `BIGINT` | Volume |
| `oi` | `BIGINT` | Open interest |

### `m_recent_daily`

Last 50 days of daily candles with SMA indicators. Source: `v_candles_1m`.

| Column | Type | Description |
|--------|------|-------------|
| `trade_date` | `DATE` | Trading date |
| `symbol` | `VARCHAR` | Symbol |
| `open` | `DOUBLE` | Day open |
| `high` | `DOUBLE` | Day high |
| `low` | `DOUBLE` | Day low |
| `close` | `DOUBLE` | Day close |
| `volume` | `BIGINT` | Day volume |
| `sma_20` | `DOUBLE` | 20-day SMA of close |
| `sma_50` | `DOUBLE` | 50-day SMA of close |
| `daily_change` | `DOUBLE` | Close change from previous day |
| `avg_volume_20` | `DOUBLE` | 20-day average volume |
| `close_5d` | `DOUBLE` | Close 5 days ago |
| `close_10d` | `DOUBLE` | Close 10 days ago |
| `close_20d` | `DOUBLE` | Close 20 days ago |

### `m_symbol_snapshot`

Latest candle per symbol with indicators (~500 rows). Source: `m_intraday`, `m_recent_daily`.

| Column | Type | Description |
|--------|------|-------------|
| `symbol` | `VARCHAR` | Symbol |
| `last_ts` | `timestamp` | Latest bar time |
| `close` | `DOUBLE` | Latest close |
| `high` | `DOUBLE` | Latest high |
| `low` | `DOUBLE` | Latest low |
| `open` | `DOUBLE` | Latest open |
| `volume` | `BIGINT` | Latest volume |
| `bars_today` | `BIGINT` | Number of intraday bars today |
| `day_high` | `DOUBLE` | Today's high |
| `day_low` | `DOUBLE` | Today's low |
| `day_open` | `DOUBLE` | Today's open |
| `day_close` | `DOUBLE` | Today's close |
| `day_volume` | `BIGINT` | Today's volume |
| `sma_20` | `DOUBLE` | 20-day SMA |
| `sma_50` | `DOUBLE` | 50-day SMA |
| `close_5d` | `DOUBLE` | Close 5 days ago |
| `close_10d` | `DOUBLE` | Close 10 days ago |
| `close_20d` | `DOUBLE` | Close 20 days ago |
| `roc_5` | `DOUBLE` | 5-day rate of change (%) |
| `roc_10` | `DOUBLE` | 10-day rate of change (%) |
| `roc_20` | `DOUBLE` | 20-day rate of change (%) |
| `trend` | `VARCHAR` | Trend classification (`Bullish`, `Bearish`, `Neutral`) |
| `relative_volume` | `DOUBLE` | Today's volume / 20-day avg volume |

### `m_intraday_snapshot`

Final scanner view with composite score and signals (~500 rows). Source: `m_symbol_snapshot`.

| Column | Type | Description |
|--------|------|-------------|
| `symbol` | `VARCHAR` | Symbol |
| `ltp` | `DOUBLE` | Last traded price |
| `day_open` | `DOUBLE` | Day open |
| `day_high` | `DOUBLE` | Day high |
| `day_low` | `DOUBLE` | Day low |
| `day_close` | `DOUBLE` | Day close |
| `day_volume` | `BIGINT` | Day volume |
| `bars_today` | `BIGINT` | Intraday bar count |
| `sma_20` | `DOUBLE` | 20-day SMA |
| `sma_50` | `DOUBLE` | 50-day SMA |
| `roc_5` | `DOUBLE` | 5-day rate of change (%) |
| `roc_10` | `DOUBLE` | 10-day rate of change (%) |
| `roc_20` | `DOUBLE` | 20-day rate of change (%) |
| `trend` | `VARCHAR` | Trend classification |
| `relative_volume` | `DOUBLE` | Relative volume ratio |
| `close_5d` | `DOUBLE` | Close 5 days ago |
| `close_10d` | `DOUBLE` | Close 10 days ago |
| `close_20d` | `DOUBLE` | Close 20 days ago |
| `rsi_approx` | `DOUBLE` | Approximate RSI (scaled from ROC) |
| `atr_approx` | `DOUBLE` | Approximate ATR (day range) |
| `intraday_score` | `DOUBLE` | Composite intraday score (0-100) |
| `signal` | `VARCHAR` | Signal (`BUY`, `SELL`, `BREAKOUT`, `NEUTRAL`) |

### `m_trading_days`

Distinct (symbol, trade_date) pairs from full Parquet history. Source: `v_candles_1m`.

| Column | Type | Description |
|--------|------|-------------|
| `symbol` | `VARCHAR` | Symbol |
| `trade_date` | `DATE` | Trading date |

### `m_duplicate_candles`

Grouped duplicate timestamp counts. Source: `v_candles_1m`.

| Column | Type | Description |
|--------|------|-------------|
| `symbol` | `VARCHAR` | Symbol |
| `timestamp` | `timestamp` | Duplicate timestamp |
| `duplicate_count` | `BIGINT` | Number of duplicates at this timestamp |

### `m_missing_candles`

Per-symbol, per-date count of present minutes. Source: `v_candles_1m`.

| Column | Type | Description |
|--------|------|-------------|
| `symbol` | `VARCHAR` | Symbol |
| `trade_date` | `DATE` | Trading date |
| `minute_count` | `BIGINT` | Number of distinct 1m bars present (max 375) |

### `m_pcr`

Put-Call Ratio per (timestamp, underlying, expiry). Source: option Parquet files (`market_data/options/candles/`).

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | `timestamp` | Bar time |
| `underlying` | `VARCHAR` | Underlying index |
| `expiry_kind` | `VARCHAR` | Expiry kind |
| `expiry_code` | `INTEGER` | Expiry code |
| `expiry_date` | `VARCHAR` | Expiry date |
| `spot` | `DOUBLE` | Underlying spot price |
| `interval_min` | `INTEGER` | Bar interval |
| `total_ce_volume` | `BIGINT` | Total call volume |
| `total_pe_volume` | `BIGINT` | Total put volume |
| `total_ce_oi` | `BIGINT` | Total call OI |
| `total_pe_oi` | `BIGINT` | Total put OI |

### `m_max_pain`

Max Pain strike per (timestamp, underlying, expiry). Source: option Parquet files.

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | `timestamp` | Bar time |
| `underlying` | `VARCHAR` | Underlying index |
| `expiry_kind` | `VARCHAR` | Expiry kind |
| `expiry_code` | `INTEGER` | Expiry code |
| `expiry_date` | `VARCHAR` | Expiry date |
| `spot` | `DOUBLE` | Underlying spot |
| `interval_min` | `INTEGER` | Bar interval |
| `max_pain_strike` | `DOUBLE` | Strike minimizing total pain |
| `total_pain_at_max_pain` | `DOUBLE` | Total option holder loss at max pain strike |

### `m_iv_surface`

ATM IV, OTM put/call IV, and IV skew. Source: option Parquet files.

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | `timestamp` | Bar time |
| `underlying` | `VARCHAR` | Underlying index |
| `expiry_kind` | `VARCHAR` | Expiry kind |
| `expiry_code` | `INTEGER` | Expiry code |
| `expiry_date` | `VARCHAR` | Expiry date |
| `spot` | `DOUBLE` | Underlying spot |
| `interval_min` | `INTEGER` | Bar interval |
| `atm_strike` | `DOUBLE` | ATM strike |
| `atm_iv` | `DOUBLE` | ATM implied volatility |
| `otm_put_iv` | `DOUBLE` | OTM put IV (average) |
| `otm_call_iv` | `DOUBLE` | OTM call IV (average) |
| `days_to_expiry` | `INTEGER` | Days to expiry from bar timestamp |

---

## Trade Journal Schema (SQLite)

Database: `market_data/journal.sqlite` (WAL mode). Table: `trade_journal`.
Managed by `datalake/journal.py:TradeJournal`.

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| `trade_id` | `TEXT` | No | Primary key | `trade_20240625_093000_a1b2` |
| `symbol` | `TEXT` | No | Traded symbol | `RELIANCE` |
| `strategy` | `TEXT` | No | Strategy name | `momentum_breakout` |
| `entry_time` | `TEXT` | No | ISO-8601 entry timestamp | `2024-06-25T09:30:00` |
| `exit_time` | `TEXT` | Yes | ISO-8601 exit timestamp | `2024-06-25T10:15:00` |
| `entry_price` | `REAL` | No | Entry price in rupees | `2510.50` |
| `exit_price` | `REAL` | Yes | Exit price in rupees | `2535.00` |
| `quantity` | `INTEGER` | No | Number of shares/contracts | `100` |
| `side` | `TEXT` | No | Trade side | `BUY`, `SELL` |
| `pnl` | `REAL` | Yes | Realised P&L in rupees | `2450.00` |
| `pnl_pct` | `REAL` | Yes | P&L percentage | `0.98` |
| `status` | `TEXT` | Yes | Trade status | `OPEN`, `CLOSED` |
| `notes` | `TEXT` | Yes | Free-text notes | `Breakout above resistance` |
| `metadata` | `TEXT` | Yes | JSON metadata blob | `{"market_regime":"bullish"}` |

---

## Order Management Schema (SQLite)

Database: `market_data/oms_orders.sqlite`. Table: `orders`.
Managed by `application/oms/persistence/sqlite_order_store.py:SqliteOrderStore`.

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| `order_id` | `TEXT` | No | Primary key | `250625000123456` |
| `correlation_id` | `TEXT` | Yes | Correlation/tracking ID | `strat_run_abc123` |
| `symbol` | `TEXT` | No | Traded symbol | `RELIANCE` |
| `exchange` | `TEXT` | No | Exchange code | `NSE` |
| `side` | `TEXT` | No | Order side | `BUY`, `SELL` |
| `order_type` | `TEXT` | No | Order type | `MARKET`, `LIMIT`, `SL`, `SLM` |
| `product_type` | `TEXT` | No | Product type | `DELIVERY`, `INTRADAY`, `CNC`, `MIS`, `NRML` |
| `quantity` | `INTEGER` | No | Ordered quantity | `100` |
| `filled_quantity` | `INTEGER` | No | Filled quantity | `75` |
| `price` | `TEXT` | No | Order price as decimal string | `2510.50` |
| `avg_price` | `TEXT` | No | Average fill price as decimal string | `2512.25` |
| `status` | `TEXT` | No | Order status | `PENDING`, `OPEN`, `PARTIALLY_FILLED`, `FILLED`, `CANCELLED`, `REJECTED` |
| `timestamp` | `TEXT` | Yes | ISO-8601 order timestamp | `2024-06-25T09:30:00` |
| `reject_reason` | `TEXT` | Yes | Rejection reason (if rejected) | `Insufficient margin` |

Index: `idx_orders_correlation` on `correlation_id`.

---

## Backtest Results Schema (SQLite)

Database: `market_data/backtest_results.sqlite`. Table: `backtest_results`.
Managed by `datalake/backtest_cache_store.py:BacktestCacheStore`.

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| `run_id` | `TEXT` | No | Primary key | `bt_20240625_093000_nifty50` |
| `symbol` | `TEXT` | No | Backtested symbol | `RELIANCE` |
| `timeframe` | `TEXT` | No | Candle timeframe | `1m` |
| `payload` | `TEXT` | No | JSON-serialized `BacktestResultResponse` | `{"run_id":"bt_...","metrics":{...}}` |
| `created_at` | `TIMESTAMP` | Yes | Auto-inserted creation timestamp | `2024-06-25 09:30:00` |

Retention: capped at `MAX_CACHE_ENTRIES = 500` rows.

---

## DuckDB Views

### Base Market Views (`analytics/views/base.py`)

#### `v_candles_1m`

Standardized 1-minute candle view reading from Hive-partitioned Parquet.

```sql
CREATE OR REPLACE VIEW v_candles_1m AS
SELECT
    timestamp, symbol, 'NSE' as exchange,
    open, high, low, close, volume, 0 as oi
FROM read_parquet('market_data/equities/candles/timeframe=1m/symbol=*/data.parquet')
```

Columns: `timestamp`, `symbol`, `exchange`, `open`, `high`, `low`, `close`, `volume`, `oi`.

#### `v_daily_summary`

Daily OHLCV aggregates from 1m candles.

```sql
CREATE OR REPLACE VIEW v_daily_summary AS
SELECT
    CAST(timestamp AS DATE) as trade_date, symbol,
    FIRST(open ORDER BY timestamp) as day_open,
    MAX(high) as day_high, MIN(low) as day_low,
    LAST(close ORDER BY timestamp) as day_close,
    SUM(volume) as day_volume, SUM(oi) as day_oi
FROM v_candles_1m
GROUP BY CAST(timestamp AS DATE), symbol
```

Columns: `trade_date`, `symbol`, `day_open`, `day_high`, `day_low`, `day_close`, `day_volume`, `day_oi`.

#### `v_latest_candle`

Most recent candle per symbol.

```sql
CREATE OR REPLACE VIEW v_latest_candle AS
SELECT c.* FROM v_candles_1m c
INNER JOIN (
    SELECT symbol, MAX(timestamp) as max_ts
    FROM v_candles_1m GROUP BY symbol
) latest ON c.symbol = latest.symbol AND c.timestamp = latest.max_ts
```

Columns: `timestamp`, `symbol`, `open`, `high`, `low`, `close`, `volume`, `oi`.

### Feature Views (`analytics/views/features.py`)

#### `v_feature_atr`

Average True Range (14, 20, 50-period).

```sql
WITH tr AS (
    SELECT symbol, timestamp,
        GREATEST(high - low,
            ABS(high - LAG(close) OVER (PARTITION BY symbol ORDER BY timestamp)),
            ABS(low - LAG(close) OVER (PARTITION BY symbol ORDER BY timestamp))
        ) as true_range
    FROM v_candles_1m
)
SELECT symbol, timestamp,
    AVG(true_range) OVER (PARTITION BY symbol ORDER BY timestamp ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) as atr_14,
    AVG(true_range) OVER (PARTITION BY symbol ORDER BY timestamp ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as atr_20,
    AVG(true_range) OVER (PARTITION BY symbol ORDER BY timestamp ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) as atr_50
FROM tr
```

Columns: `symbol`, `timestamp`, `atr_14`, `atr_20`, `atr_50`.

#### `v_feature_vwap`

Volume-weighted average price.

```sql
WITH daily AS (
    SELECT symbol, CAST(timestamp AS DATE) as trade_date, timestamp, close, volume,
        (high + low + close) / 3.0 as typical_price,
        SUM(volume) OVER (PARTITION BY symbol, CAST(timestamp AS DATE) ORDER BY timestamp ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as cum_volume
    FROM v_candles_1m
)
SELECT symbol, timestamp,
    SUM(typical_price * volume) OVER (PARTITION BY symbol, trade_date ORDER BY timestamp ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) / NULLIF(cum_volume, 0) as vwap,
    close as current_close
FROM daily
```

Columns: `symbol`, `timestamp`, `vwap`, `current_close`.

#### `v_feature_volume`

Volume analytics with moving averages and spikes.

Columns: `symbol`, `timestamp`, `volume`, `avg_volume_20`, `avg_volume_50`, `relative_volume`, `volume_spike`.

#### `v_feature_momentum`

Rate of change (5, 10, 20-period).

Columns: `symbol`, `timestamp`, `close`, `close_5d_ago`, `close_10d_ago`, `close_20d_ago`, `roc_5`, `roc_10`, `roc_20`.

#### `v_feature_rsi`

Relative Strength Index (14, 21-period).

Columns: `symbol`, `timestamp`, `rsi_14`, `rsi_21`.

### Scanner Views (`analytics/views/scanner.py`)

#### `v_intraday_vwap`

Intraday VWAP from `m_intraday`.

Columns: `symbol`, `timestamp`, `close`, `volume`, `vwap`, `distance_from_vwap`.

#### `v_intraday_rsi`

Intraday RSI (14) from `m_intraday`.

Columns: `symbol`, `timestamp`, `close`, `avg_gain_14`, `avg_loss_14`, `rsi_14`.

#### `v_intraday_atr`

Intraday ATR (14) from `m_intraday`.

Columns: `symbol`, `timestamp`, `high`, `low`, `close`, `true_range`, `atr_14`.

#### `v_intraday_snapshot`

Passthrough to `m_intraday_snapshot`.

```sql
SELECT * FROM m_intraday_snapshot
```

Columns: same as `m_intraday_snapshot`.

#### `v_top3_candidates`

Top 3 stocks by intraday score from `m_intraday_snapshot`.

Columns: `symbol`, `ltp`, `intraday_score`, `signal`, `trend`, `rsi_14`, `roc_5`, `relative_volume`, `day_high`, `day_low`, `day_volume`.

#### `v_top10_candidates`

Top 10 stocks by intraday score. Same schema as `v_top3_candidates`, LIMIT 10.

### Strategy Views (`analytics/views/strategy.py`)

#### `v_strategy_halftrend`

HalfTrend-style signals with stop-loss and target levels.

Columns: `symbol`, `ltp`, `intraday_score`, `signal`, `trend`, `rsi_14`, `roc_5`, `relative_volume`, `atr_14`, `day_high`, `day_low`, `stop_loss`, `target`.

#### `v_strategy_candidates`

Combined scanner and features for strategy, including risk metrics and position sizing.

Columns: `symbol`, `ltp`, `intraday_score`, `signal`, `trend`, `rsi_14`, `roc_5`, `roc_10`, `roc_20`, `relative_volume`, `sma_20`, `sma_50`, `atr_14`, `day_open`, `day_high`, `day_low`, `day_close`, `day_volume`, `bars_today`, `atr_pct`, `range_pct`, `suggested_quantity`.

#### `v_strategy_momentum`

Momentum signals with entry/exit levels.

Columns: `symbol`, `ltp`, `intraday_score`, `signal`, `trend`, `rsi_14`, `roc_5`, `roc_10`, `relative_volume`, `atr_14`, `momentum_signal`, `entry_level`, `target_level`.

#### `v_strategy_breakout`

Breakout signals with breakout levels, targets, and stops.

Columns: `symbol`, `ltp`, `intraday_score`, `signal`, `trend`, `rsi_14`, `relative_volume`, `roc_5`, `atr_14`, `day_high`, `day_low`, `breakout_level`, `breakout_target`, `breakout_stop`.

### Quality Views (`analytics/views/quality.py`)

#### `v_missing_candles`

Missing candle detection. Reads from `m_missing_candles`.

Columns: `symbol`, `trade_date`, `minute_count`, `status`.

`status` classification: `INCOMPLETE` (< 345 minutes), `PARTIAL` (< 375 minutes), `COMPLETE` (375 minutes).

#### `v_duplicate_candles`

Duplicate timestamp detection. Reads from `m_duplicate_candles`.

Columns: `symbol`, `timestamp`, `duplicate_count`.

#### `v_quality_score`

Per-symbol trust score (0-100). Formula: `(1 - missing_minutes / total_possible) * (1 - duplicate_count / total_possible) * 100`.

Columns: `symbol`, `trading_days`, `first_candle`, `last_candle`, `duplicate_count`, `missing_count`, `quality_score`.

### Option Views (`analytics/views/options_views.py`)

#### `v_pcr`

Put-Call Ratio (volume + OI) from `m_pcr`.

Columns: `timestamp`, `underlying`, `expiry_kind`, `expiry_code`, `expiry_date`, `spot`, `total_ce_volume`, `total_pe_volume`, `total_ce_oi`, `total_pe_oi`, `pcr_volume`, `pcr_oi`.

#### `v_max_pain`

Max Pain from `m_max_pain`.

Columns: `timestamp`, `underlying`, `expiry_kind`, `expiry_code`, `expiry_date`, `spot`, `max_pain_strike`, `total_pain_at_max_pain`, `distance_from_spot`, `position_vs_spot`.

#### `v_iv_surface`

IV term structure and skew from `m_iv_surface`.

Columns: `timestamp`, `underlying`, `expiry_kind`, `expiry_code`, `expiry_date`, `spot`, `atm_strike`, `atm_iv`, `otm_put_iv`, `otm_call_iv`, `iv_skew`, `put_call_iv_ratio`, `days_to_expiry`.

### Legacy Views (`datalake/views.py`)

#### `all_candles`

Raw read of all 1m Parquet files.

```sql
CREATE OR REPLACE VIEW all_candles AS
SELECT * FROM read_parquet('market_data/equities/candles/timeframe=1m/symbol=*/data.parquet')
```

Columns: same as OHLCV Candle core schema.

#### `latest_candles`

Most recent candle per symbol via subquery.

#### `daily_summary`

Daily OHLCV aggregates (similar to `v_daily_summary` but reads directly from `all_candles`).

#### `nifty500_universe`

Distinct symbols from all_candles.

#### `data_quality_summary`

Row counts, date ranges, zero-volume bars, OHLC errors per symbol.

---

## CSV Files

### `data/universes/`

Legacy universe CSV files (single column: `symbol`).

| File | Description | Symbols |
|------|-------------|---------|
| `nifty50.csv` | NIFTY 50 index constituents | ~50 |
| `nifty100.csv` | NIFTY 100 index constituents | ~100 |
| `nifty200.csv` | NIFTY 200 index constituents | ~200 |
| `nifty500.csv` | NIFTY 500 index constituents | ~500 |

These are the legacy source. The authoritative source is the `universe_symbols` table in DuckDB.

### `data/sectors/`

Sector classification CSVs. Most contain a single `symbol` column (one symbol per row).

| File | Description | Column(s) |
|------|-------------|-----------|
| `auto.csv` | Auto sector | `symbol` |
| `banking.csv` | Banking sector | `symbol` |
| `capitalgoods.csv` | Capital Goods sector | `symbol` |
| `cement.csv` | Cement sector | `symbol` |
| `chemicals.csv` | Chemicals sector | `symbol` |
| `consumerdur.csv` | Consumer Durables sector | `symbol` |
| `consumerservices.csv` | Consumer Services sector | `symbol` |
| `finance.csv` | Finance sector | `symbol` |
| `fmcg.csv` | FMCG sector | `symbol` |
| `infra.csv` / `infrastructure.csv` | Infrastructure sector | `symbol` |
| `it.csv` | IT sector | `symbol` |
| `media.csv` | Media sector | `symbol` |
| `metals.csv` | Metals sector | `symbol` |
| `misc.csv` | Miscellaneous sector | `symbol` |
| `nifty_sector_mapping.csv` | Full sector mapping (symbol → sector) | `symbol`, `sector` |
| `oilgas.csv` | Oil & Gas sector | `symbol` |
| `pharma.csv` | Pharma sector | `symbol` |
| `platform.csv` | Platform companies | `symbol` |
| `power.csv` | Power sector | `symbol` |
| `realty.csv` | Realty sector | `symbol` |
| `retail.csv` | Retail sector | `symbol` |
| `services.csv` | Services sector | `symbol` |
| `telecom.csv` | Telecom sector | `symbol` |
| `textiles.csv` | Textiles sector | `symbol` |

---

## Directory Layout

```
market_data/                          # Primary data lake root
├── catalog.duckdb                    # DuckDB catalog database
├── equities/candles/                 # Hive-partitioned equity candles
│   └── timeframe=1m/
│       └── symbol={SYMBOL}/
│           └── data.parquet
├── options/candles/                  # Hive-partitioned option candles
│   └── underlying={UNDERLYING}/
│       ├── WEEK/
│       │   └── {code}/
│       │       └── data.parquet
│       └── MONTH/
│           └── {code}/
│               └── data.parquet
├── journal.sqlite                    # Trade journal (SQLite, WAL mode)
├── oms_orders.sqlite                 # Order management (SQLite)
├── backtest_results.sqlite           # Backtest result cache (SQLite)
├── materialized/                     # [OBSOLETE] Old materialized path
└── _quarantine/                      # Corrupted / unparseable files

analytics_cache/                      # Materialized analytics (Parquet)
└── versions/
    ├── m_intraday/
    ├── m_recent_daily/
    ├── m_symbol_snapshot/
    ├── m_intraday_snapshot/
    ├── m_trading_days/
    ├── m_duplicate_candles/
    ├── m_missing_candles/
    ├── m_pcr/
    ├── m_max_pain/
    └── m_iv_surface/

data/
├── universes/                        # Legacy universe CSV files
│   ├── nifty50.csv
│   ├── nifty100.csv
│   ├── nifty200.csv
│   └── nifty500.csv
└── sectors/                          # Sector classification CSVs
    ├── banking.csv
    ├── it.csv
    ├── pharma.csv
    └── ... (25 files total)

datalake/                             # Python library
├── catalog.py                        # DataCatalog (DuckDB metadata)
├── schema.py                         # Canonical schemas
├── journal.py                        # TradeJournal (SQLite)
├── scan_store.py                     # Scan result persistence (DuckDB)
├── backtest_cache_store.py           # Backtest cache (SQLite)
├── views.py                          # Legacy DuckDB views
├── option_format.py                  # Option data format helpers
├── options_analytics_sql.py          # Option analytics SQL queries
├── migrations.py                     # Schema migrations
├── paths.py                          # Canonical path helpers
└── ...

analytics/views/                      # DuckDB analytics views
├── base.py                           # Base market views
├── features.py                       # Feature indicators
├── scanner.py                        # Scanner views
├── strategy.py                       # Strategy views
├── quality.py                        # Data quality views
├── options_views.py                  # Option analytics views
└── manager.py                        # ViewManager orchestration
```
