"""CandlestickPattern feature integrates into a FeaturePipeline.

File-per-guarantee: confirms the feature adds pattern columns to any
FeaturePipeline output and runs deterministically.
"""

from __future__ import annotations

import pandas as pd
import pytest

from analytics.pipeline.features import CandlestickPattern
from analytics.pipeline.pipeline import FeaturePipeline
from domain.indicators.patterns import PatternColumns


def _ohlcv(n: int = 20) -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-01", periods=n, freq="min")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0 + i * 0.1 for i in range(n)],
            "high": [101.0 + i * 0.1 for i in range(n)],
            "low": [99.0 + i * 0.1 for i in range(n)],
            "close": [100.5 + i * 0.1 for i in range(n)],
            "volume": [1000 + i for i in range(n)],
        }
    )


def test_feature_adds_pattern_columns() -> None:
    pipe = FeaturePipeline().add(CandlestickPattern())
    out = pipe.run(_ohlcv())
    for col in PatternColumns.ALL:
        assert col in out.columns


def test_feature_combines_with_existing_features() -> None:
    from analytics.pipeline.features import ATR, RSI

    pipe = FeaturePipeline().add(RSI(period=14)).add(ATR(period=14)).add(CandlestickPattern())
    out = pipe.run(_ohlcv())
    assert "rsi" in out.columns
    assert "atr" in out.columns
    for col in PatternColumns.ALL:
        assert col in out.columns


def test_feature_is_deterministic() -> None:
    pipe = FeaturePipeline().add(CandlestickPattern())
    a = pipe.run(_ohlcv())
    b = pipe.run(_ohlcv())
    pd.testing.assert_frame_equal(a, b)


def test_feature_requires_ohlcv() -> None:
    # The pipeline swallows per-feature errors (fail_closed=False), so assert
    # the feature's own contract directly.
    with pytest.raises(ValueError):
        CandlestickPattern().compute(pd.DataFrame({"close": [1.0, 2.0]}))
