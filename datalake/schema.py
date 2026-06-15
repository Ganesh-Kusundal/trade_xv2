"""Canonical candle schema — broker-agnostic, used across all modules."""

from __future__ import annotations

import pyarrow as pa

# Canonical column names
CANONICAL_COLUMNS = [
    "timestamp",    # ISO-8601 string or pd.Timestamp
    "symbol",       # NSE symbol (e.g., "RELIANCE")
    "exchange",     # "NSE", "BSE", "NFO"
    "open",         # Price in rupees
    "high",
    "low",
    "close",
    "volume",       # Number of shares
    "oi",           # Open interest (0 for equities)
]

OPTIONAL_COLUMNS = [
    "vwap",         # Volume-weighted average price
    "trade_count",  # Number of trades
]

# PyArrow schema for Parquet files
ARROW_SCHEMA = pa.schema([
    pa.field("timestamp", pa.timestamp("ns")),
    pa.field("symbol", pa.utf8()),
    pa.field("exchange", pa.utf8()),
    pa.field("open", pa.float64()),
    pa.field("high", pa.float64()),
    pa.field("low", pa.float64()),
    pa.field("close", pa.float64()),
    pa.field("volume", pa.int64()),
    pa.field("oi", pa.int64()),
])

# Trade_J schema (source)
TRADEJ_SCHEMA = {
    "symbol": "symbol",
    "bar_time_ms": "timestamp_ms",
    "open_paisa": "open_paisa",
    "high_paisa": "high_paisa",
    "low_paisa": "low_paisa",
    "close_paisa": "close_paisa",
    "volume": "volume",
}

# Hive partition path template
HIVE_PARTITION_TEMPLATE = (
    "equities/candles/timeframe={timeframe}/symbol={symbol}"
)

# Supported timeframes
TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "1d", "1w"]

# Universe files
UNIVERSE_DIR = "data/universes"
UNIVERSE_FILES = {
    "NIFTY50": f"{UNIVERSE_DIR}/nifty50.csv",
    "NIFTY100": f"{UNIVERSE_DIR}/nifty100.csv",
    "NIFTY200": f"{UNIVERSE_DIR}/nifty200.csv",
    "NIFTY500": f"{UNIVERSE_DIR}/nifty500.csv",
}
