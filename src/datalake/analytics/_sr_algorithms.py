"""Pure functions for support/resistance computation and CLI entry point."""

from __future__ import annotations

import argparse
import logging
from datetime import date

import pandas as pd

from datalake.analytics.support_resistance import PriceLevel, SupportResistance

logger = logging.getLogger(__name__)


def find_pivots(
    daily: pd.DataFrame, window: int = 2
) -> tuple[list[tuple[date, float]], list[tuple[date, float]]]:
    """Find pivot highs (resistance) and pivot lows (support).

    A pivot high at index i: high[i] > all other highs in window.
    A pivot low at index i: low[i] < all other lows in window.
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


def cluster_levels(
    pivots: list[tuple[date, float]], tolerance: float = 0.01, level_type: str = "support"
) -> list[PriceLevel]:
    """Cluster nearby pivots and return ranked levels."""
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
                level_type=level_type,
            )
        )

    levels.sort(key=lambda lvl: (-lvl.touches, lvl.price))
    return levels


def main() -> None:
    """CLI entry point for precomputing support/resistance levels."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Precompute support/resistance levels")
    parser.add_argument("--force", action="store_true", help="Force recomputation")
    parser.add_argument("--days", type=int, default=252, help="Lookback days")
    parser.add_argument("--symbols", nargs="*", help="Specific symbols")
    args = parser.parse_args()

    sr = SupportResistance()
    stats = sr.precompute(
        symbols=args.symbols,
        days=args.days,
        force=args.force,
    )
    logger.info("Done: %s", stats)


if __name__ == "__main__":
    main()
