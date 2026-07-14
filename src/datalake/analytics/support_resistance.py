"""Precomputed support/resistance levels for all symbols.

Computes daily pivot-based S/R levels and stores as partitioned Parquet
for fast point-in-time queries. Refreshes on data sync.

Algorithm:
  1. Read daily OHLC from the datalake
  2. Find pivot highs (resistance) and pivot lows (support)
  3. Cluster nearby pivots within tolerance
  4. Rank by touch frequency (more touches = stronger level)
  5. Store as Parquet with (symbol, level_type, price, touches, last_touch)

Usage:
    # Precompute for all symbols
    python -m datalake.analytics.support_resistance --force

    # Query programmatically
    from datalake.analytics.support_resistance import SupportResistance
    sr = SupportResistance()
    levels = sr.get_levels("RELIANCE", days=60)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa

from datalake.core.duckdb_utils import DEFAULT_CATALOG_PATH, duckdb_connection
from datalake.core.io import atomic_parquet_write
from datalake.core.symbols import normalize_symbol

logger = logging.getLogger(__name__)

from domain.ports.data_catalog import DEFAULT_DATA_PATHS

FEATURES_ROOT = DEFAULT_DATA_PATHS.features_root
SR_DIR = FEATURES_ROOT / "support_resistance"


@dataclass(frozen=True)
class PriceLevel:
    """A support or resistance price level."""
    price: float
    touches: int
    last_touch: date
    level_type: str  # "support" or "resistance"


class SupportResistance:
    """Precomputed support/resistance levels backed by Parquet.

    Usage:
        sr = SupportResistance()
        levels = sr.get_levels("RELIANCE", days=60, top_n=5)
        # Returns: {"support": [PriceLevel(...)], "resistance": [PriceLevel(...)]}
    """

    def __init__(
        self,
        catalog_path: str | Path = DEFAULT_CATALOG_PATH,
        features_root: Path = FEATURES_ROOT,
    ) -> None:
        self._catalog_path = str(catalog_path)
        self._features_root = features_root
        self._sr_dir = features_root / "support_resistance"

    # ── Query API ─────────────────────────────────────────────────────────

    def get_levels(
        self,
        symbol: str,
        days: int = 60,
        top_n: int = 5,
        pivot_window: int = 2,
        cluster_tolerance: float = 0.01,
    ) -> dict[str, list[PriceLevel]]:
        """Get support/resistance levels for a symbol.

        Args:
            symbol: NSE symbol.
            days: Lookback window in days.
            top_n: Number of levels to return.
            pivot_window: Window for pivot detection.
            cluster_tolerance: Fraction for clustering (0.01 = 1%).

        Returns:
            Dict with "support" and "resistance" lists of PriceLevel.
        """
        symbol = normalize_symbol(symbol)

        # Try precomputed first
        levels = self._read_precomputed(symbol)
        if levels:
            return self._filter_levels(levels, days, top_n)

        # Fallback to on-the-fly computation
        return self._compute_on_the_fly(
            symbol, days, top_n, pivot_window, cluster_tolerance
        )

    def get_levels_batch(
        self,
        symbols: list[str],
        days: int = 60,
        top_n: int = 3,
    ) -> dict[str, dict[str, list[PriceLevel]]]:
        """Get S/R levels for multiple symbols.

        Returns:
            Dict mapping symbol → {"support": [...], "resistance": [...]}.
        """
        result = {}
        for symbol in symbols:
            try:
                result[symbol] = self.get_levels(symbol, days=days, top_n=top_n)
            except Exception as exc:
                logger.warning("Failed to get S/R for %s: %s", symbol, exc)
                result[symbol] = {"support": [], "resistance": []}
        return result

    def get_nearest_levels(
        self,
        symbol: str,
        current_price: float,
        days: int = 60,
    ) -> dict:
        """Get nearest support and resistance to current price.

        Returns:
            Dict with "nearest_support", "nearest_resistance", "distance_pct".
        """
        levels = self.get_levels(symbol, days=days, top_n=10)

        supports = [l for l in levels["support"] if l.price < current_price]
        resistances = [l for l in levels["resistance"] if l.price > current_price]

        nearest_support = max(supports, key=lambda l: l.price) if supports else None
        nearest_resistance = min(resistances, key=lambda l: l.price) if resistances else None

        distance_pct = None
        if nearest_support and nearest_resistance:
            (nearest_resistance.price - nearest_support.price) / current_price * 100
            position = (current_price - nearest_support.price) / (nearest_resistance.price - nearest_support.price) * 100
            distance_pct = round(position, 1)

        return {
            "symbol": symbol,
            "current_price": current_price,
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
            "position_in_range_pct": distance_pct,
        }

    # ── Precomputation ────────────────────────────────────────────────────

    def precompute(
        self,
        symbols: list[str] | None = None,
        days: int = 252,
        pivot_window: int = 2,
        cluster_tolerance: float = 0.01,
        force: bool = False,
    ) -> dict:
        """Precompute S/R levels for all symbols.

        Args:
            symbols: Specific symbols to compute. None = all from catalog.
            days: Lookback window (default 252 = 1 year).
            pivot_window: Pivot detection window.
            cluster_tolerance: Clustering tolerance.
            force: Force recomputation even if data exists.

        Returns:
            Dict with computation stats.
        """
        if not force and self._sr_dir.exists() and list(self._sr_dir.rglob("*.parquet")):
            logger.info("S/R data already exists, skipping (use --force to recompute)")
            return {"skipped": True}

        if symbols is None:
            symbols = self._list_symbols_from_catalog()

        logger.info("Precomputing S/R for %d symbols", len(symbols))
        start = time.time()

        all_levels = []
        errors = 0

        for i, symbol in enumerate(symbols, 1):
            try:
                levels = self._compute_levels_for_symbol(
                    symbol, days, pivot_window, cluster_tolerance
                )
                all_levels.extend(levels)
                if i % 50 == 0:
                    logger.info("  Progress: %d/%d symbols", i, len(symbols))
            except Exception as exc:
                logger.warning("Failed for %s: %s", symbol, exc)
                errors += 1

        # Write to Parquet
        if all_levels:
            self._write_parquet(all_levels)

        elapsed = time.time() - start
        stats = {
            "symbols_processed": len(symbols),
            "symbols_with_errors": errors,
            "total_levels": len(all_levels),
            "elapsed_seconds": round(elapsed, 1),
        }
        logger.info("S/R precomputation complete: %s", stats)
        return stats

    def _compute_levels_for_symbol(
        self,
        symbol: str,
        days: int,
        pivot_window: int,
        cluster_tolerance: float,
    ) -> list[dict]:
        """Compute S/R levels for a single symbol."""
        from datalake.analytics._sr_algorithms import find_pivots, cluster_levels

        with duckdb_connection(self._catalog_path, read_only=True) as conn:
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)

            daily = self._read_daily_candles(conn, symbol, start_date, end_date)
            if daily.empty or len(daily) < 2 * pivot_window + 1:
                return []

            supports, resistances = find_pivots(daily, window=pivot_window)
            support_levels = cluster_levels(supports, tolerance=cluster_tolerance, level_type="support")
            resistance_levels = cluster_levels(resistances, tolerance=cluster_tolerance, level_type="resistance")

            levels = []
            for lvl in support_levels:
                levels.append({
                    "symbol": symbol,
                    "level_type": "support",
                    "price": lvl.price,
                    "touches": lvl.touches,
                    "last_touch": lvl.last_touch,
                    "computed_at": datetime.now(),
                })
            for lvl in resistance_levels:
                levels.append({
                    "symbol": symbol,
                    "level_type": "resistance",
                    "price": lvl.price,
                    "touches": lvl.touches,
                    "last_touch": lvl.last_touch,
                    "computed_at": datetime.now(),
                })

            return levels

    def _read_daily_candles(
        self,
        conn: duckdb.DuckDBPyConnection,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Read daily OHLC from the datalake."""
        try:
            return conn.execute(
                """
                SELECT
                    CAST(timestamp AS DATE) as date,
                    MAX(high) as high,
                    MIN(low) as low,
                    (ARRAY_AGG(close ORDER BY timestamp DESC))[1] as close
                FROM all_candles
                WHERE symbol = ?
                  AND CAST(timestamp AS DATE) BETWEEN ? AND ?
                GROUP BY CAST(timestamp AS DATE)
                ORDER BY date
                """,
                [symbol, start_date, end_date],
            ).fetchdf()
        except Exception:
            # Fallback: try v_daily_summary if it exists
            try:
                return conn.execute(
                    """
                    SELECT trade_date as date, day_high as high, day_low as low, day_close as close
                    FROM v_daily_summary
                    WHERE symbol = ? AND trade_date BETWEEN ? AND ?
                    ORDER BY trade_date
                    """,
                    [symbol, start_date, end_date],
                ).fetchdf()
            except Exception:
                return pd.DataFrame()

    def _read_precomputed(self, symbol: str) -> list[PriceLevel]:
        """Read precomputed levels from Parquet."""
        parquet_path = self._sr_dir / "levels.parquet"
        if not parquet_path.exists():
            return []

        try:
            df = pd.read_parquet(parquet_path)
            df = df[df["symbol"] == symbol]
            if df.empty:
                return []

            levels = []
            for _, row in df.iterrows():
                lt = row["last_touch"]
                if hasattr(lt, "date"):
                    lt = lt.date()
                levels.append(PriceLevel(
                    price=float(row["price"]),
                    touches=int(row["touches"]),
                    last_touch=lt,
                    level_type=row["level_type"],
                ))
            return levels
        except Exception:
            return []

    def _filter_levels(
        self,
        levels: list[PriceLevel],
        days: int,
        top_n: int,
    ) -> dict[str, list[PriceLevel]]:
        """Filter levels by recency and return top N."""
        cutoff = datetime.now().date() - timedelta(days=days)

        def _to_date(d):
            if hasattr(d, "date"):
                return d.date()
            import numpy as np
            if isinstance(d, np.datetime64):
                return pd.Timestamp(d).date()
            return d

        supports = sorted(
            [l for l in levels if l.level_type == "support" and _to_date(l.last_touch) >= cutoff],
            key=lambda l: (-l.touches, -l.price),
        )
        resistances = sorted(
            [l for l in levels if l.level_type == "resistance" and _to_date(l.last_touch) >= cutoff],
            key=lambda l: (-l.touches, l.price),
        )

        return {
            "support": supports[:top_n],
            "resistance": resistances[:top_n],
        }

    def _write_parquet(self, levels: list[dict]) -> None:
        """Write levels to partitioned Parquet."""
        self._sr_dir.mkdir(parents=True, exist_ok=True)

        df = pd.DataFrame(levels)
        table = pa.Table.from_pandas(df, preserve_index=False)

        atomic_parquet_write(
            self._sr_dir / "levels.parquet",
            table,
            compression="snappy",
        )
        logger.info("Wrote %d levels to %s", len(levels), self._sr_dir)

    def _compute_on_the_fly(
        self,
        symbol: str,
        days: int,
        top_n: int,
        pivot_window: int,
        cluster_tolerance: float,
    ) -> dict[str, list[PriceLevel]]:
        """Compute S/R levels on-the-fly from daily candles."""
        from datalake.analytics._sr_algorithms import find_pivots, cluster_levels

        with duckdb_connection(self._catalog_path, read_only=True) as conn:
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)

            daily = self._read_daily_candles(conn, symbol, start_date, end_date)
            if daily.empty or len(daily) < 2 * pivot_window + 1:
                return {"support": [], "resistance": []}

            supports, resistances = find_pivots(daily, window=pivot_window)
            support_levels = cluster_levels(supports, tolerance=cluster_tolerance, level_type="support")
            resistance_levels = cluster_levels(resistances, tolerance=cluster_tolerance, level_type="resistance")

            return {
                "support": support_levels[:top_n],
                "resistance": resistance_levels[:top_n],
            }

    def _list_symbols_from_catalog(self) -> list[str]:
        """Get all symbols from the catalog."""
        try:
            with duckdb_connection(self._catalog_path, read_only=True) as conn:
                result = conn.execute(
                    "SELECT DISTINCT symbol FROM symbols ORDER BY symbol"
                ).fetchall()
                return [r[0] for r in result]
        except Exception:
            return []


def main() -> None:
    """CLI entry point for precomputing support/resistance levels."""
    from datalake.analytics._sr_algorithms import main as _legacy_main

    _legacy_main()


if __name__ == "__main__":
    main()
