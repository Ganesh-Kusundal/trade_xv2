from __future__ import annotations

import pandas as pd

from analytics.volume_profile.volume_profile import VolumeProfileBuilder


def test_volume_profile_poc() -> None:
    rows = []
    index = 0
    for price in range(90, 111):
        volume = 100 if price != 100 else 10_000
        for _ in range(3):
            rows.append(
                {
                    "timestamp": pd.Timestamp("2026-01-01") + pd.Timedelta(minutes=index),
                    "open": price,
                    "high": price + 1,
                    "low": price - 1,
                    "close": price,
                    "volume": volume,
                }
            )
            index += 1
    data = pd.DataFrame(rows)

    result = VolumeProfileBuilder(bins=20).build(data, symbol="NIFTY")

    assert 99 <= result.metrics["poc"] <= 101
    assert result.metrics["vah"] >= result.metrics["val"]
