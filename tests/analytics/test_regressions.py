from __future__ import annotations

import math

import pandas as pd

from analytics.indicators.technical import historical_volatility, rsi


def test_rsi_regression_known_values() -> None:
    prices = pd.Series([44, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28])
    values = rsi(prices, period=14).dropna().tolist()

    assert len(values) == 1
    assert round(values[0], 2) == 72.98


def test_historical_volatility_regression() -> None:
    prices = pd.Series([100.0, 101.0, 100.5, 102.0, 103.0, 102.5, 104.0, 105.0])
    values = historical_volatility(prices, periods=5, annualization=1).dropna().tolist()

    assert len(values) == 3
    assert all(math.isfinite(value) for value in values)
