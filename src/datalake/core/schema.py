"""Canonical candle schema — broker-agnostic, used across all modules.

All timestamps are stored as **naive datetime in IST (Asia/Kolkata),
microsecond precision (``us``)**. The source data may be in any timezone
or precision, but must be converted before writing — see
:func:`enforce_canonical_schema`, called by every writer before
``atomic_parquet_write``.
"""

from __future__ import annotations

from datetime import date

# Session constants removed from constants.py (ADR-005 / G3).
# Import from datalake.exchange_registry if needed:
#   from datalake.exchange_registry import (
#       get_market_open_time, get_market_close_time, get_session_minutes,
#   )

import pyarrow as pa

# Canonical column names
CANONICAL_COLUMNS = [
    "timestamp",  # Naive datetime in IST (Asia/Kolkata)
    "symbol",  # NSE symbol (e.g., "RELIANCE"), uppercased, stripped
    "exchange",  # "NSE", "BSE", "NFO"
    "open",  # Price in rupees
    "high",
    "low",
    "close",
    "volume",  # Number of shares
    "oi",  # Open interest (0 for equities)
    "event_time",  # When the event occurred (identical to timestamp for candles)
]

# Temporal columns for point-in-time safety (metadata, not candle data)
TEMPORAL_COLUMNS = [
    "event_time",      # When the event actually occurred (identical to timestamp for candles)
    "published_at",    # When this version of the bar became available
    "ingested_at",     # When the system ingested this bar version
    "is_correction",   # Boolean flag: true if this replaces a previous version
]

OPTIONAL_COLUMNS = [
    "vwap",  # Volume-weighted average price
    "trade_count",  # Number of trades
]

# NSE market hours in IST (defined in :mod:`datalake.core.constants`).

# PyArrow schema for Parquet files.
#
# Timestamp unit is ``us`` (microsecond) -- chosen to match what
# ingestion actually produces (Python `datetime` objects are
# microsecond-precision) rather than the previously-declared `ns`, which
# no writer ever honored: see `enforce_canonical_schema` below.
ARROW_SCHEMA = pa.schema(
    [
        pa.field("timestamp", pa.timestamp("us")),
        pa.field("symbol", pa.utf8()),
        pa.field("exchange", pa.utf8()),
        pa.field("open", pa.float64()),
        pa.field("high", pa.float64()),
        pa.field("low", pa.float64()),
        pa.field("close", pa.float64()),
        pa.field("volume", pa.int64()),
        pa.field("oi", pa.int64()),
        pa.field("event_time", pa.timestamp("us")),
        pa.field("published_at", pa.timestamp("us")),
        pa.field("ingested_at", pa.timestamp("us")),
        pa.field("is_correction", pa.bool_()),
    ]
)


def enforce_canonical_schema(table: pa.Table) -> pa.Table:
    """Cast every timestamp-typed column present in *table* to the
    canonical unit (``ARROW_SCHEMA``'s declared type for that column).

    Every writer must call this immediately before
    :func:`infrastructure.io.parquet.atomic_parquet_write` so the
    physical unit on disk always matches ``ARROW_SCHEMA``, regardless of
    what unit the source data happened to arrive in (Python `datetime`
    objects -> `us`; broker epoch-ms fields explicitly parsed with
    `pd.to_datetime(..., unit="ms")` -> `ms`; etc).

    Only touches columns that are both present in *table* and declared
    as a timestamp type in ``ARROW_SCHEMA`` -- unknown/extra columns
    pass through unchanged.
    """
    canonical_by_name = {f.name: f for f in ARROW_SCHEMA}
    new_fields = []
    for field in table.schema:
        canonical = canonical_by_name.get(field.name)
        if canonical is not None and pa.types.is_timestamp(canonical.type):
            new_fields.append(pa.field(field.name, canonical.type, nullable=field.nullable))
        else:
            new_fields.append(field)
    target_schema = pa.schema(new_fields)
    if target_schema.equals(table.schema):
        return table
    return table.cast(target_schema)

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
HIVE_PARTITION_TEMPLATE = "equities/candles/timeframe={timeframe}/symbol={symbol}"

# Supported timeframes
TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "1d", "1w"]

# Universe files — CSV paths kept as legacy migration source.
# DuckDB (``universe_symbols`` table via :class:`DataCatalog`)
# is the authoritative source. The CSV files in ``data/universes/``
# are retained for bootstrapping and may be removed once migration
# is complete.
UNIVERSE_DIR = "data/universes"
UNIVERSE_FILES: dict[str, str] = {
    "NIFTY50": f"{UNIVERSE_DIR}/nifty50.csv",
    "NIFTY100": f"{UNIVERSE_DIR}/nifty100.csv",
    "NIFTY200": f"{UNIVERSE_DIR}/nifty200.csv",
    "NIFTY500": f"{UNIVERSE_DIR}/nifty500.csv",
}

# Cached universe symbols — populated lazily by load_universe().
_universe_cache: dict[tuple[str, date | None], list[str]] = {}


def load_universe(universe: str, catalog=None, as_of_date=None) -> list[str]:
    """Load symbol list from DuckDB, falling back to CSV.

    DuckDB (``universe_symbols`` table) is the authoritative source.
    The CSV files in :data:`UNIVERSE_FILES` are a legacy fallback
    for bootstrapping only.

    If *as_of_date* is provided, returns universe membership as of that
    historical date (point-in-time safe). Otherwise returns current membership.

    Results are cached in ``_universe_cache`` for repeated calls.

    Args:
        universe: Universe name (NIFTY50, NIFTY100, NIFTY200, NIFTY500).
        catalog: Optional DuckDB catalog connection.
        as_of_date: Optional historical date for point-in-time query.

    Returns:
        List of uppercase symbol strings.
    """
    cache_key = (universe, as_of_date)
    if cache_key in _universe_cache:
        return _universe_cache[cache_key]

    symbols: list[str] = []

    if catalog is not None:
        try:
            if as_of_date is not None:
                from datalake.storage.catalog import DataCatalog

                if isinstance(catalog, DataCatalog):
                    rows = catalog.get_universe_as_of(universe, as_of_date)
                else:
                    rows = catalog.execute("""
                        SELECT symbol FROM universe_history
                        WHERE universe = ?
                          AND effective_date <= ?
                          AND (end_date IS NULL OR end_date > ?)
                        ORDER BY symbol
                    """, [universe, as_of_date, as_of_date]).fetchall()
                if rows:
                    symbols = [s.upper() for s in rows]
                    _universe_cache[cache_key] = symbols
                    return symbols
            else:
                rows = catalog.execute(
                    "SELECT symbol FROM universe_symbols WHERE universe = ? ORDER BY symbol",
                    [universe],
                ).fetchall()
                if rows:
                    symbols = [r[0].upper() for r in rows]
                    _universe_cache[cache_key] = symbols
                    return symbols
        except (OSError, RuntimeError):
            pass

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
                except OSError:
                    pass

    return symbols
