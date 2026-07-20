"""Tests for domain→API candle mapping performance and correctness (ADR-020)."""

from __future__ import annotations

import time

import pandas as pd
import pytest

from domain.candles.historical import HistoricalSeries, InstrumentRef
from interface.api.candle_mapper import series_to_api_candles
from interface.api.schemas import Candle

_INSTRUMENT = InstrumentRef(symbol="TEST", exchange="NSE")


class TestCandleMapperConversion:
    """API egress must go through HistoricalSeries + series_to_api_candles."""

    def _create_test_dataframe(self, num_rows: int = 100) -> pd.DataFrame:
        now = pd.Timestamp.now()
        timestamps = pd.date_range(end=now, periods=num_rows, freq="1min")
        return pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": [100.0 + i * 0.1 for i in range(num_rows)],
                "high": [101.0 + i * 0.1 for i in range(num_rows)],
                "low": [99.0 + i * 0.1 for i in range(num_rows)],
                "close": [100.5 + i * 0.1 for i in range(num_rows)],
                "volume": [1000 + i * 10 for i in range(num_rows)],
                "oi": [500 + i * 5 for i in range(num_rows)],
            }
        )

    def _mapper_conversion(self, df: pd.DataFrame) -> list[Candle]:
        series = HistoricalSeries.from_datalake_df(df, _INSTRUMENT, "1m")
        return series_to_api_candles(series)

    def test_mapper_produces_expected_count(self) -> None:
        df = self._create_test_dataframe(100)
        candles = self._mapper_conversion(df)
        assert len(candles) == 100

    def test_mapper_ohlc_values(self) -> None:
        df = self._create_test_dataframe(3)
        candles = self._mapper_conversion(df)
        assert float(candles[0].o) == pytest.approx(100.0)
        assert float(candles[1].c) == pytest.approx(100.6)
        assert candles[2].v == pytest.approx(1020.0)

    def test_mapper_rejects_nan_ohlc(self) -> None:
        df = self._create_test_dataframe(1)
        df.loc[0, "close"] = float("nan")
        with pytest.raises(ValueError, match="NaN or missing OHLCV"):
            self._mapper_conversion(df)

    def test_mapper_empty_dataframe(self) -> None:
        df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
        candles = self._mapper_conversion(df)
        assert candles == []

    def test_mapper_performance_1000_rows(self) -> None:
        df = self._create_test_dataframe(1000)
        start = time.perf_counter()
        candles = self._mapper_conversion(df)
        elapsed = time.perf_counter() - start
        assert len(candles) == 1000
        assert elapsed < 2.0, f"Mapper too slow: {elapsed:.2f}s for 1000 rows"
