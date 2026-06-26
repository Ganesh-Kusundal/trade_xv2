"""Universe management — symbol list loading from DuckDB/CSV.

Extracted from schema.py to enforce SRP: schema.py owns column
definitions; universe.py owns symbol list resolution.

Supports:
- DuckDB (universe_symbols table) as authoritative source
- CSV fallback for bootstrapping
- Point-in-time membership queries via universe_history
- In-memory caching for repeated calls
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

UNIVERSE_DIR = "data/universes"
UNIVERSE_FILES: dict[str, str] = {
    "NIFTY50": f"{UNIVERSE_DIR}/nifty50.csv",
    "NIFTY100": f"{UNIVERSE_DIR}/nifty100.csv",
    "NIFTY200": f"{UNIVERSE_DIR}/nifty200.csv",
    "NIFTY500": f"{UNIVERSE_DIR}/nifty500.csv",
}

_universe_cache: dict[tuple[str, date | None], list[str]] = {}


def load_universe(universe: str, catalog=None, as_of_date=None) -> list[str]:
    """Load symbol list from DuckDB, falling back to CSV.

    DuckDB (``universe_symbols`` table) is the authoritative source.
    The CSV files in ``UNIVERSE_FILES`` are a legacy fallback for bootstrapping.

    If *as_of_date* is provided, returns universe membership as of that
    historical date (point-in-time safe). Otherwise returns current membership.

    Results are cached for repeated calls.

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
                from datalake.catalog import DataCatalog

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
