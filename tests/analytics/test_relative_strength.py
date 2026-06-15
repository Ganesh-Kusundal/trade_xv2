from __future__ import annotations

import pandas as pd

from analytics.features.relative_strength import RelativeStrengthAnalyzer


def _series(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=len(values), freq="D"),
            "open": values,
            "high": [v + 1 for v in values],
            "low": [v - 1 for v in values],
            "close": values,
            "volume": [1000] * len(values),
        }
    )


def test_relative_strength_classifies_strong_asset() -> None:
    asset = _series([100 + i * 2 for i in range(30)])
    benchmark = _series([100 + (i % 3) * 0.2 for i in range(30)])

    result = RelativeStrengthAnalyzer(period=10).analyze("RELIANCE", asset, benchmark, "NIFTY")

    assert result.signals == ["Strong"]
    assert result.scores["relative_strength"] >= 60
