from __future__ import annotations

import time

import pandas as pd
import pytest

from analytics.core.feature_builder import FeatureBuilder


@pytest.mark.performance
def test_feature_builder_benchmark_1000_bars() -> None:
    rows = []
    for index in range(1000):
        close = 100 + index * 0.01
        rows.append(
            {
                "timestamp": pd.Timestamp("2026-01-01") + pd.Timedelta(minutes=index),
                "open": close - 0.1,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "volume": 1000 + index % 50,
            }
        )
    data = pd.DataFrame(rows)
    builder = FeatureBuilder()

    start = time.perf_counter()
    result = builder.build(data, symbol="NIFTY")
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert not result.data.empty
    assert elapsed_ms < 1000
