"""Historical series gap-free validation for certification."""

from __future__ import annotations

from typing import Any


def assert_gap_free_historical(series: Any, *, timeframe: str) -> int:
    """Validate monotonic timestamps and no explicit gaps. Returns bar count."""
    gaps = getattr(series, "gaps", None) or []
    if gaps:
        raise RuntimeError(f"historical gaps detected for {timeframe}: {len(gaps)}")

    if getattr(series, "is_degraded", False):
        raise RuntimeError(f"degraded historical series for {timeframe}")

    bars = getattr(series, "bars", None)
    if bars is None:
        bars = getattr(series, "candles", None)
    if bars is None and hasattr(series, "__len__"):
        try:
            n = len(series)
        except TypeError:
            n = 0
        if n <= 0:
            raise RuntimeError(f"no {timeframe} history")
        return n

    if not bars:
        raise RuntimeError(f"no {timeframe} history")

    timestamps: list[Any] = []
    for bar in bars:
        ts = getattr(bar, "timestamp", None) or getattr(bar, "time", None)
        if ts is not None:
            timestamps.append(ts)

    for i in range(1, len(timestamps)):
        if timestamps[i] <= timestamps[i - 1]:
            raise RuntimeError(f"non-monotonic timestamps in {timeframe} history")

    return len(bars)
