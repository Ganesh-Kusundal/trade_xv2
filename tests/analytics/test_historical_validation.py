from __future__ import annotations

import pandas as pd

from analytics.core.feature_builder import FeatureBuilder
from analytics.options.options_analytics import OptionsAnalytics


def test_historical_validation_ohlcv_contract() -> None:
    data = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=30, freq="D"),
            "open": range(100, 130),
            "high": [value + 2 for value in range(100, 130)],
            "low": [value - 2 for value in range(100, 130)],
            "close": range(101, 131),
            "volume": [1000] * 30,
        }
    )

    result = FeatureBuilder().build(data, symbol="RELIANCE")

    assert list(result.data.columns)[:7] == ["timestamp", "open", "high", "low", "close", "volume", "oi"]
    assert result.data["symbol"].iloc[-1] == "RELIANCE"
    assert len(result.data) == 30


def test_historical_validation_option_chain_contract() -> None:
    chain = pd.DataFrame(
        [
            {"strike": 100, "option_type": "CE", "oi": 10, "change_in_oi": 1, "volume": 10, "iv": 20, "ltp": 5, "ltp_change": 1},
            {"strike": 100, "option_type": "PE", "oi": 20, "change_in_oi": -1, "volume": 10, "iv": 22, "ltp": 6, "ltp_change": -1},
        ]
    )

    result = OptionsAnalytics().analyze("NIFTY", chain, spot_price=100)

    assert "pcr" in result.metrics
    assert "current_max_pain" in result.metrics
    assert result.metrics["pcr"] == 2.0
