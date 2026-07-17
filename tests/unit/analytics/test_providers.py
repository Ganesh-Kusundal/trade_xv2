"""Tests for market data providers."""

from __future__ import annotations

import pandas as pd

from analytics.core.providers import CsvMarketDataProvider, DataFrameMarketDataProvider


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=5),
            "open": [100, 101, 102, 103, 104],
            "high": [102, 103, 104, 105, 106],
            "low": [99, 100, 101, 102, 103],
            "close": [101, 102, 103, 104, 105],
            "volume": [1000, 1100, 1200, 1300, 1400],
        }
    )


def test_dataframe_provider_history() -> None:
    provider = DataFrameMarketDataProvider(history={"RELIANCE": _sample_df()})
    result = provider.history("RELIANCE")
    assert len(result) == 5
    assert provider.history("TCS").empty


def test_dataframe_provider_option_chain() -> None:
    provider = DataFrameMarketDataProvider(
        history={},
        option_chains={"NIFTY": {"strikes": [{"strike": 100}]}},
    )
    result = provider.option_chain("NIFTY")
    assert len(result.strikes) == 1
    assert len(provider.option_chain("BANKNIFTY").strikes) == 0


def test_dataframe_provider_ltp() -> None:
    provider = DataFrameMarketDataProvider(history={}, prices={"RELIANCE": 2500.0})
    assert provider.ltp("RELIANCE") == 2500.0
    assert provider.ltp("TCS") == 0.0


def test_csv_provider_with_symbol_column(tmp_path) -> None:
    df = pd.DataFrame(
        {
            "symbol": ["RELIANCE", "RELIANCE", "TCS", "TCS"],
            "timestamp": pd.date_range("2026-01-01", periods=4),
            "open": [100, 101, 200, 201],
            "high": [102, 103, 202, 203],
            "low": [99, 100, 199, 200],
            "close": [101, 102, 201, 202],
            "volume": [1000, 1100, 2000, 2100],
        }
    )
    csv_path = tmp_path / "data.csv"
    df.to_csv(csv_path, index=False)

    provider = CsvMarketDataProvider(csv_path, symbol_column="symbol")
    reliance = provider.history("RELIANCE")
    assert len(reliance) == 2
    tcs = provider.history("TCS")
    assert len(tcs) == 2


def test_csv_provider_caches(tmp_path) -> None:
    df = pd.DataFrame(
        {
            "symbol": ["A", "A"],
            "timestamp": pd.date_range("2026-01-01", periods=2),
            "open": [100, 101],
            "high": [102, 103],
            "low": [99, 100],
            "close": [101, 102],
            "volume": [1000, 1100],
        }
    )
    csv_path = tmp_path / "data.csv"
    df.to_csv(csv_path, index=False)

    provider = CsvMarketDataProvider(csv_path, symbol_column="symbol")
    r1 = provider.history("A")
    r2 = provider.history("A")
    assert r1 is r2
