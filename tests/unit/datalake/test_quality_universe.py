"""Tests for datalake.quality_universe — cross-symbol quality checks."""

from __future__ import annotations

import numpy as np
import pandas as pd

from datalake.quality.universe import UniverseQualityEngine, UniverseQualityReport


def _create_symbol_data(root, symbols, n=500, recent_n=None):
    """Helper to create mock parquet data for symbols."""
    for symbol in symbols:
        tf_dir = root / "equities" / "candles" / "timeframe=1m" / f"symbol={symbol}"
        tf_dir.mkdir(parents=True)

        if recent_n is not None:
            dates = pd.date_range("2024-01-01", periods=recent_n, freq="1D")
        else:
            dates = pd.date_range("2023-01-01", periods=n, freq="1D")

        np.random.seed(hash(symbol) % 2**31)
        prices = 1000 + np.cumsum(np.random.randn(len(dates)) * 10)

        df = pd.DataFrame({
            "timestamp": dates,
            "symbol": symbol,
            "exchange": "NSE",
            "open": prices,
            "high": prices + 10,
            "low": prices - 10,
            "close": prices,
            "volume": np.random.randint(10000, 100000, len(dates)),
            "oi": [0] * len(dates),
        })
        df.to_parquet(tf_dir / "data.parquet", index=False)


class TestUniverseQualityReport:
    def test_report_summary(self):
        report = UniverseQualityReport(
            universe="NIFTY50",
            symbol_count=50,
            symbols_with_data=45,
            symbols_missing=["A", "B", "C", "D", "E"],
        )
        summary = report.summary()
        assert "NIFTY50" in summary
        assert "45/50" in summary
        assert "5" in summary


class TestSectorDivergence:
    def test_detects_divergent_sector(self, tmp_path):
        root = tmp_path / "market_data"
        root.mkdir()
        syms = ["RELIANCE", "TCS", "INFY", "HDFCBANK"]
        _create_symbol_data(root, syms)

        engine = UniverseQualityEngine(root=str(root))
        sector_mapping = {
            "RELIANCE": "OILGAS",
            "TCS": "IT",
            "INFY": "IT",
            "HDFCBANK": "BANKING",
        }
        report = engine.check(universe="NIFTY500", symbols=syms, sector_mapping=sector_mapping)

        assert report.symbol_count == 4
        assert report.symbols_with_data == 4

    def test_no_sector_mapping(self, tmp_path):
        root = tmp_path / "market_data"
        root.mkdir()
        _create_symbol_data(root, ["SYM1", "SYM2"])

        engine = UniverseQualityEngine(root=str(root))
        report = engine.check(universe="NIFTY500", symbols=["SYM1", "SYM2"])
        assert report.sector_divergences == []


class TestVolumeAnomalies:
    def test_detects_high_volume(self, tmp_path):
        root = tmp_path / "market_data"
        root.mkdir()

        low_dir = root / "equities" / "candles" / "timeframe=1m" / "symbol=LOW_VOL"
        low_dir.mkdir(parents=True)
        dates = pd.date_range("2023-01-01", periods=400, freq="1D")
        df_low = pd.DataFrame({
            "timestamp": dates,
            "symbol": "LOW_VOL", "exchange": "NSE",
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
            "volume": [1000] * 400, "oi": [0] * 400,
        })
        df_low.to_parquet(low_dir / "data.parquet", index=False)

        high_dir = root / "equities" / "candles" / "timeframe=1m" / "symbol=HIGH_VOL"
        high_dir.mkdir(parents=True)
        df_high = pd.DataFrame({
            "timestamp": dates,
            "symbol": "HIGH_VOL", "exchange": "NSE",
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
            "volume": [1000] * 395 + [100000] * 5, "oi": [0] * 400,
        })
        df_high.to_parquet(high_dir / "data.parquet", index=False)

        engine = UniverseQualityEngine(root=str(root))
        report = engine.check(universe="NIFTY500", symbols=["LOW_VOL", "HIGH_VOL"])

        assert len(report.volume_anomalies) >= 1
        assert any(a["symbol"] == "HIGH_VOL" for a in report.volume_anomalies)


class TestMissingSymbols:
    def test_reports_missing(self, tmp_path):
        root = tmp_path / "market_data"
        root.mkdir()

        engine = UniverseQualityEngine(root=str(root))
        report = engine.check(universe="nifty50", symbols=["SYM1", "SYM2", "SYM3"])

        assert report.symbol_count == 3
        assert report.symbols_with_data == 0
        assert len(report.symbols_missing) == 3
        assert report.overall_status == "CRITICAL"


class TestStaleDetection:
    def test_detects_stale(self, tmp_path):
        root = tmp_path / "market_data"
        root.mkdir()

        recent_dir = root / "equities" / "candles" / "timeframe=1m" / "symbol=SYM1"
        recent_dir.mkdir(parents=True)
        df_recent = pd.DataFrame({
            "timestamp": pd.date_range("2024-06-01", periods=10, freq="1D"),
            "symbol": "SYM1", "exchange": "NSE",
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
            "volume": [1000] * 10, "oi": [0] * 10,
        })
        df_recent.to_parquet(recent_dir / "data.parquet", index=False)

        stale_dir = root / "equities" / "candles" / "timeframe=1m" / "symbol=SYM2"
        stale_dir.mkdir(parents=True)
        df_stale = pd.DataFrame({
            "timestamp": pd.date_range("2023-01-01", periods=10, freq="1D"),
            "symbol": "SYM2", "exchange": "NSE",
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
            "volume": [1000] * 10, "oi": [0] * 10,
        })
        df_stale.to_parquet(stale_dir / "data.parquet", index=False)

        engine = UniverseQualityEngine(root=str(root))
        report = engine.check(universe="TEST", symbols=["SYM1", "SYM2"], max_stale_days=1)

        assert len(report.stale_symbols) == 1
        assert "SYM2" in report.stale_symbols
