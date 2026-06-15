from __future__ import annotations

import pandas as pd

from analytics.core.feature_builder import FeatureBuilder


def _prices(close_start: float = 100.0) -> pd.DataFrame:
    closes = [close_start + i * 1.5 for i in range(40)]
    highs = [close + 2 for close in closes]
    lows = [close - 2 for close in closes]
    opens = [close - 0.5 for close in closes]
    volumes = [1000 + (i % 5) * 100 for i in range(40)]
    volumes[-1] = 5000
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=40, freq="D"),
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )


def test_feature_builder_adds_expected_features() -> None:
    result = FeatureBuilder(volume_bars=10).build(_prices(), symbol="RELIANCE")

    assert not result.data.empty
    assert {"rsi", "relative_volume", "volume_spike", "trend", "market_structure"}.issubset(result.data.columns)
    assert bool(result.data.iloc[-1]["volume_spike"]) is True
    assert result.summary["last_close"] == 158.5


def test_normalize_ohlcv_rejects_missing_columns() -> None:
    from analytics.core.models import normalize_ohlcv

    try:
        normalize_ohlcv(pd.DataFrame({"timestamp": [1], "close": [100]}))
    except ValueError as exc:
        assert "open" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
