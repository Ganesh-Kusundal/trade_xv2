"""Regression: cache_to_parquet must normalize UTC-aware broker timestamps to naive IST."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from infrastructure.historical_data import HistoricalDataService


@dataclass
class _Candle:
    timestamp: datetime
    open: float = 100.0
    high: float = 101.0
    low: float = 99.0
    close: float = 100.5
    volume: int = 1000


def test_cache_to_parquet_normalizes_utc_aware_to_naive_ist(tmp_path: Path) -> None:
    service = HistoricalDataService(client=object())
    path = tmp_path / "cache.parquet"

    # Broker epoch: 2026-01-15 03:45 UTC == 09:15 IST
    utc_ts = datetime(2026, 1, 15, 3, 45, tzinfo=timezone.utc)
    service.cache_to_parquet([_Candle(timestamp=utc_ts)], path)

    df = pd.read_parquet(path)
    stored = df["timestamp"].iloc[0]

    assert stored == pd.Timestamp("2026-01-15 09:15:00")
    assert getattr(stored, "tzinfo", None) is None
