"""Tests for datalake.converter — Trade_J → canonical conversion."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from datalake.converter import convert_tradej_directory, convert_tradej_parquet


def _make_tradej_parquet(
    path: Path,
    symbol: str = "TEST",
    n: int = 10,
    start: str = "2026-01-01",
) -> None:
    """Create a synthetic Trade_J Parquet file with valid OHLC."""
    np.random.seed(42)
    close = 10000 + np.cumsum(np.random.randn(n) * 100)  # paise
    high_offset = np.abs(np.random.randint(50, 200, n))
    low_offset = np.abs(np.random.randint(50, 200, n))
    open_offset = np.random.randint(-50, 50, n)
    df = pd.DataFrame(
        {
            "bar_time_ms": pd.date_range(start, periods=n, freq="1min").astype(np.int64) // 10**6,
            "open_paisa": close.astype(np.int64) + open_offset,
            "high_paisa": close.astype(np.int64) + high_offset,
            "low_paisa": close.astype(np.int64) - low_offset,
            "close_paisa": close.astype(np.int64),
            "volume": np.random.randint(100, 10000, n),
            "interval": "1m",
            "ingested_at_ms": np.zeros(n, dtype=np.int64),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


class TestConvertSingleFile:
    def test_basic_conversion(self, tmp_path: Path) -> None:
        src = tmp_path / "data.parquet"
        _make_tradej_parquet(src, "TEST")

        result = convert_tradej_parquet(src, "TEST")

        assert len(result) == 10
        assert list(result.columns) == [
            "timestamp",
            "symbol",
            "exchange",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "oi",
            "event_time",
            "published_at",
            "ingested_at",
            "is_correction",
        ]

    def test_paise_to_rupees(self, tmp_path: Path) -> None:
        src = tmp_path / "data.parquet"
        _make_tradej_parquet(src, "TEST")

        result = convert_tradej_parquet(src, "TEST")

        # Prices should be divided by 100
        assert result["close"].mean() < 200  # was ~100 in paise, now ~100 in rupees
        assert result["close"].mean() > 50

    def test_timestamp_is_datetime(self, tmp_path: Path) -> None:
        src = tmp_path / "data.parquet"
        _make_tradej_parquet(src, "TEST")

        result = convert_tradej_parquet(src, "TEST")

        assert pd.api.types.is_datetime64_any_dtype(result["timestamp"])

    def test_symbol_and_exchange_added(self, tmp_path: Path) -> None:
        src = tmp_path / "data.parquet"
        _make_tradej_parquet(src, "RELIANCE")

        result = convert_tradej_parquet(src, "RELIANCE", "NSE")

        assert (result["symbol"] == "RELIANCE").all()
        assert (result["exchange"] == "NSE").all()

    def test_oi_defaults_to_zero(self, tmp_path: Path) -> None:
        src = tmp_path / "data.parquet"
        _make_tradej_parquet(src, "TEST")

        result = convert_tradej_parquet(src, "TEST")

        assert (result["oi"] == 0).all()

    def test_drops_tradej_columns(self, tmp_path: Path) -> None:
        src = tmp_path / "data.parquet"
        _make_tradej_parquet(src, "TEST")

        result = convert_tradej_parquet(src, "TEST")

        # Trade_J-specific columns should not be in output
        assert "interval" not in result.columns
        assert "ingested_at_ms" not in result.columns
        assert "bar_time_ms" not in result.columns
        assert "open_paisa" not in result.columns

    def test_ohlc_relationships_preserved(self, tmp_path: Path) -> None:
        src = tmp_path / "data.parquet"
        _make_tradej_parquet(src, "TEST")

        result = convert_tradej_parquet(src, "TEST")

        # High should be >= open and close
        assert (result["high"] >= result["open"]).all()
        assert (result["high"] >= result["close"]).all()
        # Low should be <= open and close
        assert (result["low"] <= result["open"]).all()
        assert (result["low"] <= result["close"]).all()

    def test_sorted_by_timestamp(self, tmp_path: Path) -> None:
        src = tmp_path / "data.parquet"
        _make_tradej_parquet(src, "TEST")

        result = convert_tradej_parquet(src, "TEST")

        timestamps = result["timestamp"].tolist()
        assert timestamps == sorted(timestamps)


class TestConvertDirectory:
    def test_batch_conversion(self, tmp_path: Path) -> None:
        tradej_dir = tmp_path / "tradej" / "bars"
        target_dir = tmp_path / "market_data" / "equities" / "candles" / "timeframe=1m"

        # Create 3 symbol directories
        for sym in ["RELIANCE", "TCS", "HDFCBANK"]:
            sym_dir = tradej_dir / f"symbol={sym}"
            _make_tradej_parquet(sym_dir / "2026-01.parquet", sym, n=20)

        results = convert_tradej_directory(tradej_dir, target_dir)

        assert len(results) == 3
        assert results["RELIANCE"]["rows"] == 20
        assert results["TCS"]["rows"] == 20
        assert results["HDFCBANK"]["rows"] == 20

        # Check hive layout
        assert (target_dir / "symbol=RELIANCE" / "data.parquet").exists()
        assert (target_dir / "symbol=TCS" / "data.parquet").exists()

    def test_selective_conversion(self, tmp_path: Path) -> None:
        tradej_dir = tmp_path / "tradej" / "bars"
        target_dir = tmp_path / "market_data"

        for sym in ["RELIANCE", "TCS"]:
            sym_dir = tradej_dir / f"symbol={sym}"
            _make_tradej_parquet(sym_dir / "2026-01.parquet", sym, n=10)

        results = convert_tradej_directory(tradej_dir, target_dir, symbols=["RELIANCE"])

        assert len(results) == 1
        assert "RELIANCE" in results

    def test_empty_directory(self, tmp_path: Path) -> None:
        tradej_dir = tmp_path / "empty"
        target_dir = tmp_path / "output"
        tradej_dir.mkdir()

        results = convert_tradej_directory(tradej_dir, target_dir)

        assert len(results) == 0

    def test_multiple_monthly_files_merged(self, tmp_path: Path) -> None:
        tradej_dir = tmp_path / "tradej" / "bars"
        target_dir = tmp_path / "market_data"
        sym_dir = tradej_dir / "symbol=TEST"

        # Create 3 monthly files with different start dates
        _make_tradej_parquet(sym_dir / "2026-01.parquet", "TEST", n=10, start="2026-01-01")
        _make_tradej_parquet(sym_dir / "2026-02.parquet", "TEST", n=10, start="2026-02-01")
        _make_tradej_parquet(sym_dir / "2026-03.parquet", "TEST", n=10, start="2026-03-01")

        results = convert_tradej_directory(tradej_dir, target_dir)

        assert results["TEST"]["rows"] == 30  # 10 + 10 + 10

    def test_duplicates_removed(self, tmp_path: Path) -> None:
        tradej_dir = tmp_path / "tradej" / "bars"
        target_dir = tmp_path / "market_data"
        sym_dir = tradej_dir / "symbol=TEST"

        # Create two files with overlapping timestamps
        _make_tradej_parquet(sym_dir / "a.parquet", "TEST", n=10)
        _make_tradej_parquet(sym_dir / "b.parquet", "TEST", n=10)

        results = convert_tradej_directory(tradej_dir, target_dir)

        # Should deduplicate by timestamp
        assert results["TEST"]["rows"] <= 20
        assert results["TEST"]["duplicates_dropped"] == 10
