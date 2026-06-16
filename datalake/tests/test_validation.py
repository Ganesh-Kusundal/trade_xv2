"""Tests for candle validation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from datalake.schema import CANONICAL_COLUMNS
from datalake.validation import validate_candles, validate_parquet_file


def _valid_df(n: int = 10) -> pd.DataFrame:
    """Create a valid candle DataFrame."""
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01 09:15", periods=n, freq="1min"),
        "symbol": "TEST",
        "exchange": "NSE",
        "open": [100.0] * n,
        "high": [101.0] * n,
        "low": [99.0] * n,
        "close": [100.5] * n,
        "volume": [1000] * n,
        "oi": [0] * n,
    })


class TestValidateCandlesValid:
    def test_valid_data_unchanged(self) -> None:
        df = _valid_df()
        result = validate_candles(df, symbol="TEST")
        assert len(result) == 10

    def test_empty_dataframe(self) -> None:
        df = pd.DataFrame(columns=CANONICAL_COLUMNS)
        result = validate_candles(df, symbol="TEST")
        assert len(result) == 0


class TestValidateOHLC:
    def test_drops_high_less_than_low(self) -> None:
        df = _valid_df(5)
        df.loc[2, "high"] = 90.0  # high < low (99)
        df.loc[2, "low"] = 95.0
        result = validate_candles(df, symbol="TEST", drop_invalid=True)
        assert len(result) == 4

    def test_drops_open_above_high(self) -> None:
        df = _valid_df(5)
        df.loc[3, "open"] = 105.0  # open > high (101)
        result = validate_candles(df, symbol="TEST", drop_invalid=True)
        assert len(result) == 4

    def test_drops_close_below_low(self) -> None:
        df = _valid_df(5)
        df.loc[1, "close"] = 95.0  # close < low (99)
        result = validate_candles(df, symbol="TEST", drop_invalid=True)
        assert len(result) == 4

    def test_drops_negative_prices(self) -> None:
        df = _valid_df(5)
        df.loc[0, "open"] = -1.0
        result = validate_candles(df, symbol="TEST", drop_invalid=True)
        assert len(result) == 4


class TestValidateVolume:
    def test_drops_negative_volume(self) -> None:
        df = _valid_df(5)
        df.loc[2, "volume"] = -100
        result = validate_candles(df, symbol="TEST", drop_invalid=True)
        assert len(result) == 4

    def test_zero_volume_kept(self) -> None:
        df = _valid_df(5)
        df.loc[0, "volume"] = 0
        result = validate_candles(df, symbol="TEST", drop_invalid=True)
        assert len(result) == 5  # zero is valid


class TestValidateTimestamp:
    def test_drops_null_timestamps(self) -> None:
        df = _valid_df(5)
        df.loc[2, "timestamp"] = pd.NaT
        result = validate_candles(df, symbol="TEST", drop_invalid=True)
        assert len(result) == 4

    def test_drops_future_timestamps(self) -> None:
        df = _valid_df(5)
        df.loc[0, "timestamp"] = pd.Timestamp("2099-01-01")
        result = validate_candles(df, symbol="TEST", drop_invalid=True)
        assert len(result) == 4


class TestValidateMissingColumns:
    def test_missing_required_column_raises(self) -> None:
        df = _valid_df(5)
        df = df.drop(columns=["close"])
        with pytest.raises(ValueError, match="missing required columns"):
            validate_candles(df, symbol="TEST", drop_invalid=False)


class TestValidatePriceRange:
    def test_drops_extreme_high(self) -> None:
        df = _valid_df(5)
        df.loc[1, "high"] = 1e8  # above MAX_PRICE
        result = validate_candles(df, symbol="TEST", drop_invalid=True)
        assert len(result) == 4

    def test_drops_negative_low(self) -> None:
        df = _valid_df(5)
        df.loc[0, "low"] = -1.0
        result = validate_candles(df, symbol="TEST", drop_invalid=True)
        assert len(result) == 4


class TestValidateParquetFile:
    def test_valid_file(self, tmp_path: Path) -> None:
        path = tmp_path / "valid.parquet"
        _valid_df(10).to_parquet(path, index=False)

        report = validate_parquet_file(path, symbol="TEST")
        assert report["total_rows"] == 10
        assert report["valid_rows"] == 10
        assert report["invalid_rows"] == 0
