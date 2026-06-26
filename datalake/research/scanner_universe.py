"""Load scanner universe OHLCV data from the data lake."""

from __future__ import annotations

import logging

import pandas as pd

from datalake.schema import load_universe

logger = logging.getLogger(__name__)


def load_scanner_universe(
    gateway,
    catalog,
    universe: str,
    timeframe: str = "1m",
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Load universe symbols and parallel OHLCV candles for scanner runs.

    Returns (universe_df, stats) where stats has requested/loaded/missing counts.
    """
    symbols = load_universe(universe.upper(), catalog=catalog)
    stats = {
        "requested": len(symbols),
        "loaded": 0,
        "missing": 0,
    }
    if not symbols:
        return pd.DataFrame(), stats

    candle_map = gateway.load_candles_parallel(symbols, timeframe=timeframe)
    frames: list[pd.DataFrame] = []
    for sym in symbols:
        df = candle_map.get(sym)
        if df is None or df.empty:
            stats["missing"] += 1
            continue
        frame = df.copy()
        frame["symbol"] = sym
        frames.append(frame)
        stats["loaded"] += 1

    if stats["missing"]:
        logger.warning(
            "scanner_universe_partial: universe=%s loaded=%d missing=%d",
            universe,
            stats["loaded"],
            stats["missing"],
        )

    if not frames:
        return pd.DataFrame(), stats

    return pd.concat(frames, ignore_index=True), stats
