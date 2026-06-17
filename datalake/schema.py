"""Canonical candle schema — broker-agnostic, used across all modules.

All timestamps are stored as **naive datetime in IST (Asia/Kolkata)**.
The source data may be in any timezone, but must be converted to IST
before writing. This is enforced by the converter and the quality views.
"""

from __future__ import annotations

import pyarrow as pa

# Canonical column names
CANONICAL_COLUMNS = [
    "timestamp",    # Naive datetime in IST (Asia/Kolkata)
    "symbol",       # NSE symbol (e.g., "RELIANCE"), uppercased, stripped
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

# NSE market hours in IST
MARKET_OPEN_HOUR = 9      # 9:15 IST
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15    # 15:30 IST
MARKET_CLOSE_MINUTE = 30
TRADING_MINUTES_PER_DAY = 375  # (15*60 + 30) - (9*60 + 15) + 1 = 376... actually 375 unique minute marks

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

# Universe files — CSV paths kept as migration source.
# New code should use :func:`load_universe` which reads from DuckDB
# with automatic fallback to CSV.
UNIVERSE_DIR = "data/universes"
UNIVERSE_FILES = {
    "NIFTY50": f"{UNIVERSE_DIR}/nifty50.csv",
    "NIFTY100": f"{UNIVERSE_DIR}/nifty100.csv",
    "NIFTY200": f"{UNIVERSE_DIR}/nifty200.csv",
    "NIFTY500": f"{UNIVERSE_DIR}/nifty500.csv",
}

# Cached universe symbols — populated lazily by load_universe().
_universe_cache: dict[str, list[str]] = {}


def load_universe(universe: str, catalog=None) -> list[str]:
    """Load symbol list from DuckDB, falling back to CSV.

    First checks a DuckDB ``universe_symbols`` table via *catalog*.
    If unavailable, reads from the CSV in :data:`UNIVERSE_FILES`.
    Results are cached in ``_universe_cache`` for repeated calls.

    Args:
        universe: Universe name (NIFTY50, NIFTY100, NIFTY200, NIFTY500).
        catalog: Optional DuckDB catalog connection.

    Returns:
        List of uppercase symbol strings.
    """
    if universe in _universe_cache:
        return _universe_cache[universe]

    symbols: list[str] = []

    # Try DuckDB first
    if catalog is not None:
        try:
            rows = catalog.execute(
                "SELECT symbol FROM universe_symbols WHERE universe = ? ORDER BY symbol",
                [universe],
            ).fetchall()
            if rows:
                symbols = [r[0].upper() for r in rows]
                _universe_cache[universe] = symbols
                return symbols
        except (IOError, OSError, RuntimeError):
            # DuckDB may not have the table yet or be unavailable.
            # Fall through to CSV.
            pass

    # Fall back to CSV (do NOT cache CSV results so a later DuckDB
    # call can pick up the authoritative source).
    csv_path = UNIVERSE_FILES.get(universe)
    if csv_path:
        from pathlib import Path
        import pandas as pd
        p = Path(csv_path)
        for candidate in (p, Path("..") / csv_path, Path("trade_xv2") / csv_path):
            if candidate.exists():
                try:
                    df = pd.read_csv(candidate)
                    col = "symbol" if "symbol" in df.columns else df.columns[0]
                    symbols = df[col].str.upper().tolist()
                    return symbols
                except (IOError, OSError):
                    pass

    return symbols
