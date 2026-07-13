"""Fast support/resistance detection for stocks.

One-shot API: `find_support_resistance("RELIANCE", days=20)` returns the
top 3 support and top 3 resistance levels in milliseconds.

Reads from the catalog's `v_daily_summary` view (630K rows, indexed by symbol).
Faster than reading 1m Parquet + aggregating in SQL.

Algorithm:
  1. Read daily OHLC for the symbol from v_daily_summary
  2. Find pivot points (local minima = support, local maxima = resistance)
  3. Cluster nearby pivots (within `cluster_tolerance`% of each other)
  4. Rank clusters by frequency (more touches = stronger level)
  5. Return top N support and resistance levels

Example:
    >>> from analytics.stocks.find_levels import find_support_resistance
    >>> result = find_support_resistance("RELIANCE", days=60)
    >>> for level in result["support"]:
    ...     print(f"Support: {level.price} (touched {level.touches}x)")
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from datalake.core.duckdb_utils import duckdb_connection
from domain.ports.data_catalog import DEFAULT_CATALOG_PATH

DEFAULT_CATALOG = str(DEFAULT_CATALOG_PATH)


@dataclass(frozen=True)
class PriceLevel:
    """A support or resistance price level."""

    price: float
    touches: int  # number of pivots in the cluster (strength indicator)
    last_touch: date  # date of most recent pivot in the cluster


def _read_daily_candles(
    conn: duckdb.DuckDBPyConnection, symbol: str, start_date: date, end_date: date
) -> pd.DataFrame:
    """Read daily OHLC for a symbol from v_daily_summary.

    v_daily_summary columns: trade_date, symbol, day_open, day_high, day_low, day_close, day_volume
    """
    from domain.symbols import normalize_symbol

    sym = normalize_symbol(symbol)

    return conn.execute(
        """
        SELECT
            trade_date as date,
            day_high as high,
            day_low as low,
            day_close as close
        FROM v_daily_summary
        WHERE symbol = ?
          AND trade_date BETWEEN ? AND ?
        ORDER BY trade_date
    """,
        [sym, start_date, end_date],
    ).fetchdf()


def _find_pivots(
    daily: pd.DataFrame, window: int = 2
) -> tuple[list[tuple[date, float]], list[tuple[date, float]]]:
    """Find local minima (support) and local maxima (resistance).

    Returns lists of (date, price) tuples so we can track last_touch date.
    A pivot high at index i: high[i] > high[i-window:i+window+1] (excluding i).
    A pivot low at index i: low[i] < low[i-window:i+window+1] (excluding i).
    """
    if len(daily) < 2 * window + 1:
        return [], []

    supports: list[tuple[date, float]] = []
    resistances: list[tuple[date, float]] = []
    highs = daily["high"].values
    lows = daily["low"].values
    dates = daily["date"].values

    for i in range(window, len(daily) - window):
        window_highs = [highs[j] for j in range(i - window, i + window + 1) if j != i]
        window_lows = [lows[j] for j in range(i - window, i + window + 1) if j != i]
        if highs[i] > max(window_highs):
            resistances.append((dates[i], float(highs[i])))
        if lows[i] < min(window_lows):
            supports.append((dates[i], float(lows[i])))

    return supports, resistances


def _cluster_levels(pivots: list[tuple[date, float]], tolerance: float = 0.01) -> list[PriceLevel]:
    """Cluster nearby pivot prices and return the strongest levels.

    `tolerance` is the fraction of the price (e.g., 0.01 = 1%) within which
    two pivots are considered the same level.
    """
    if not pivots:
        return []

    prices = [p for _, p in pivots]
    median_price = sorted(prices)[len(prices) // 2]
    if median_price <= 0:
        return []

    tol = median_price * tolerance
    pivots_sorted = sorted(pivots, key=lambda x: x[1])
    clusters: list[list[tuple[date, float]]] = []
    current_cluster: list[tuple[date, float]] = [pivots_sorted[0]]

    for p in pivots_sorted[1:]:
        if p[1] - current_cluster[-1][1] <= tol:
            current_cluster.append(p)
        else:
            clusters.append(current_cluster)
            current_cluster = [p]
    clusters.append(current_cluster)

    levels = []
    for cluster in clusters:
        touches = len(cluster)
        avg_price = sum(p for _, p in cluster) / len(cluster)
        last_touch = max(d for d, _ in cluster)
        levels.append(
            PriceLevel(
                price=round(avg_price, 2),
                touches=touches,
                last_touch=last_touch,
            )
        )

    # Sort by strength (touches desc), then by price
    levels.sort(key=lambda lvl: (-lvl.touches, lvl.price))
    return levels


def find_support_resistance(
    symbol: str,
    days: int = 60,
    top_n: int = 3,
    pivot_window: int = 2,
    cluster_tolerance: float = 0.01,
    catalog_path: str | Path | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> dict[str, list[PriceLevel]]:
    """Find support and resistance levels for a stock.

    Parameters
    ----------
    symbol : str
        NSE symbol (e.g., "RELIANCE", "TCS"). Will be normalized.
    days : int
        Lookback window in days. Default 60.
    top_n : int
        Number of support and resistance levels to return. Default 3.
    pivot_window : int
        Window for pivot detection (default 2 = ±2 days).
    cluster_tolerance : float
        Fraction of price for clustering pivots. Default 0.01 (1%).
    catalog_path : str | Path | None
        Override catalog path (for testing). Defaults to data/lake/catalog.duckdb.
    conn : duckdb.DuckDBPyConnection | None
        DuckDB connection (for testing). If None, opens a read-only catalog connection.

    Returns
    -------
    dict with keys "support" and "resistance", each a list of PriceLevel.
    """
    own_conn = conn is None
    if own_conn:
        cat = str(catalog_path) if catalog_path else DEFAULT_CATALOG
        with duckdb_connection(cat, read_only=True) as pool_conn:
            conn = pool_conn
            return _find_levels_inner(conn, symbol, days, pivot_window, cluster_tolerance, top_n)
    else:
        return _find_levels_inner(conn, symbol, days, pivot_window, cluster_tolerance, top_n)


def _find_levels_inner(
    conn: duckdb.DuckDBPyConnection,
    symbol: str,
    days: int,
    pivot_window: int,
    cluster_tolerance: float,
    top_n: int,
) -> dict:
    """Inner implementation for find_support_resistance."""
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    daily = _read_daily_candles(conn, symbol, start_date, end_date)
    if daily.empty:
        return {"support": [], "resistance": []}

    supports, resistances = _find_pivots(daily, window=pivot_window)
    support_levels = _cluster_levels(supports, tolerance=cluster_tolerance)
    resistance_levels = _cluster_levels(resistances, tolerance=cluster_tolerance)

    return {
        "support": support_levels[:top_n],
        "resistance": resistance_levels[:top_n],
    }
