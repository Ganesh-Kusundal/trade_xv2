"""Tests for DataQualityMonitor — consolidated single-pass query."""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from datalake.quality.monitor import DataQualityMonitor


def _write_parquet(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _init_catalog(db_path: Path) -> None:
    """Create a minimal catalog.duckdb so read_only connect works."""
    conn = duckdb.connect(str(db_path))
    conn.execute("SELECT 1")
    conn.close()


def _make_ohlcv_df(
    n: int = 375,
    symbol: str = "TEST",
    start: str = "2026-06-25 09:15",
    freq: str = "1min",
    zero_volume_frac: float = 0.0,
    ohlc_errors: int = 0,
) -> pd.DataFrame:
    """Create realistic OHLCV data for testing."""
    np.random.seed(42)
    dates = pd.date_range(start, periods=n, freq=freq)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    volume = np.random.randint(1000, 10000, n).astype(float)

    # Inject zero-volume bars
    n_zero = int(n * zero_volume_frac)
    if n_zero > 0:
        volume[:n_zero] = 0

    high = close + np.abs(np.random.randn(n) * 0.5)
    low = close - np.abs(np.random.randn(n) * 0.5)
    open_ = close + np.random.randn(n) * 0.2

    # Inject OHLC errors (high < low)
    for i in range(min(ohlc_errors, n)):
        high[i], low[i] = low[i], high[i]  # swap so high < low

    return pd.DataFrame({
        "timestamp": dates,
        "symbol": symbol,
        "exchange": "NSE",
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume.astype(np.int64),
        "oi": np.zeros(n, dtype=np.int64),
    })


class TestMonitorBasicStats:
    """Verify global stats (total_symbols, total_candles, date_range)."""

    def test_single_symbol_stats(self, tmp_path: Path) -> None:
        df = _make_ohlcv_df(n=100, symbol="AAPL")
        _write_parquet(
            tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=AAPL" / "data.parquet",
            df,
        )
        _init_catalog(tmp_path / "catalog.duckdb")

        monitor = DataQualityMonitor(root=str(tmp_path))
        report = monitor.run_checks(timeframe="1m")

        assert report.total_symbols == 1
        assert report.total_candles == 100
        assert report.date_range[0] is not None
        assert report.date_range[1] is not None

    def test_multi_symbol_stats(self, tmp_path: Path) -> None:
        for sym, n in [("AAPL", 100), ("GOOG", 200)]:
            df = _make_ohlcv_df(n=n, symbol=sym)
            _write_parquet(
                tmp_path / "equities" / "candles" / "timeframe=1m"
                / f"symbol={sym}" / "data.parquet",
                df,
            )
        _init_catalog(tmp_path / "catalog.duckdb")

        monitor = DataQualityMonitor(root=str(tmp_path))
        report = monitor.run_checks(timeframe="1m")

        assert report.total_symbols == 2
        assert report.total_candles == 300


class TestMonitorFreshness:
    """Verify freshness metric per symbol."""

    def test_fresh_data_passes(self, tmp_path: Path) -> None:
        # Use today's date so days_old = 0
        today = pd.Timestamp.now().strftime("%Y-%m-%d")
        df = _make_ohlcv_df(n=50, symbol="TEST", start=f"{today} 09:15")
        _write_parquet(
            tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=TEST" / "data.parquet",
            df,
        )
        _init_catalog(tmp_path / "catalog.duckdb")

        monitor = DataQualityMonitor(root=str(tmp_path))
        report = monitor.run_checks(timeframe="1m")

        assert len(report.symbol_reports) == 1
        sq = report.symbol_reports[0]
        assert sq.symbol == "TEST"
        fresh_metric = next(m for m in sq.metrics if m.name == "freshness")
        assert fresh_metric.status == "PASS"
        assert fresh_metric.value <= 1

    def test_stale_data_fails(self, tmp_path: Path) -> None:
        # Use a date 30 days ago
        old_date = (pd.Timestamp.now() - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
        df = _make_ohlcv_df(n=50, symbol="STALE", start=f"{old_date} 09:15")
        _write_parquet(
            tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=STALE" / "data.parquet",
            df,
        )
        _init_catalog(tmp_path / "catalog.duckdb")

        monitor = DataQualityMonitor(root=str(tmp_path))
        report = monitor.run_checks(timeframe="1m")

        sq = report.symbol_reports[0]
        fresh_metric = next(m for m in sq.metrics if m.name == "freshness")
        assert fresh_metric.status == "FAIL"
        assert fresh_metric.value >= 7


class TestMonitorCompleteness:
    """Verify completeness metric."""

    def test_full_day_passes(self, tmp_path: Path) -> None:
        # 375 candles = 1 full day of 1m data (6.25 hours * 60)
        df = _make_ohlcv_df(n=375, symbol="FULL")
        _write_parquet(
            tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=FULL" / "data.parquet",
            df,
        )
        _init_catalog(tmp_path / "catalog.duckdb")

        monitor = DataQualityMonitor(root=str(tmp_path))
        report = monitor.run_checks(timeframe="1m")

        sq = report.symbol_reports[0]
        comp_metric = next(m for m in sq.metrics if m.name == "completeness")
        assert comp_metric.status == "PASS"
        assert comp_metric.value >= 90.0

    def test_partial_day_warning(self, tmp_path: Path) -> None:
        # ~200 candles out of 375 expected → ~53% → FAIL
        df = _make_ohlcv_df(n=200, symbol="PARTIAL")
        _write_parquet(
            tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=PARTIAL" / "data.parquet",
            df,
        )
        _init_catalog(tmp_path / "catalog.duckdb")

        monitor = DataQualityMonitor(root=str(tmp_path))
        report = monitor.run_checks(timeframe="1m")

        sq = report.symbol_reports[0]
        comp_metric = next(m for m in sq.metrics if m.name == "completeness")
        # 200/375 = 53.3% → FAIL
        assert comp_metric.status == "FAIL"
        assert comp_metric.value < 90.0

    def test_unsupported_timeframe_skips_completeness(self, tmp_path: Path) -> None:
        df = _make_ohlcv_df(n=100, symbol="TEST")
        _write_parquet(
            tmp_path / "equities" / "candles" / "timeframe=1h" / "symbol=TEST" / "data.parquet",
            df,
        )
        _init_catalog(tmp_path / "catalog.duckdb")

        monitor = DataQualityMonitor(root=str(tmp_path))
        report = monitor.run_checks(timeframe="1h")

        sq = report.symbol_reports[0]
        metric_names = [m.name for m in sq.metrics]
        assert "completeness" not in metric_names


class TestMonitorIntegrity:
    """Verify integrity metrics (zero_volume, ohlc_integrity)."""

    def test_clean_data_passes(self, tmp_path: Path) -> None:
        df = _make_ohlcv_df(n=100, symbol="CLEAN")
        _write_parquet(
            tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=CLEAN" / "data.parquet",
            df,
        )
        _init_catalog(tmp_path / "catalog.duckdb")

        monitor = DataQualityMonitor(root=str(tmp_path))
        report = monitor.run_checks(timeframe="1m")

        sq = report.symbol_reports[0]
        zv_metric = next(m for m in sq.metrics if m.name == "zero_volume")
        ohlc_metric = next(m for m in sq.metrics if m.name == "ohlc_integrity")
        assert zv_metric.status == "PASS"
        assert ohlc_metric.status == "PASS"
        assert ohlc_metric.value == 0

    def test_zero_volume_detected(self, tmp_path: Path) -> None:
        # 15% zero volume → FAIL (>= 10%)
        df = _make_ohlcv_df(n=100, symbol="ZEROVOL", zero_volume_frac=0.15)
        _write_parquet(
            tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=ZEROVOL" / "data.parquet",
            df,
        )
        _init_catalog(tmp_path / "catalog.duckdb")

        monitor = DataQualityMonitor(root=str(tmp_path))
        report = monitor.run_checks(timeframe="1m")

        sq = report.symbol_reports[0]
        zv_metric = next(m for m in sq.metrics if m.name == "zero_volume")
        assert zv_metric.status == "FAIL"
        assert zv_metric.value >= 10.0

    def test_ohlc_errors_detected(self, tmp_path: Path) -> None:
        df = _make_ohlcv_df(n=100, symbol="BROKEN", ohlc_errors=5)
        _write_parquet(
            tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=BROKEN" / "data.parquet",
            df,
        )
        _init_catalog(tmp_path / "catalog.duckdb")

        monitor = DataQualityMonitor(root=str(tmp_path))
        report = monitor.run_checks(timeframe="1m")

        sq = report.symbol_reports[0]
        ohlc_metric = next(m for m in sq.metrics if m.name == "ohlc_integrity")
        assert ohlc_metric.status == "FAIL"
        assert ohlc_metric.value > 0
        assert any("OHLC" in issue for issue in sq.issues)


class TestMonitorEdgeCases:
    """Edge cases: empty data, missing directory, multiple symbols."""

    def test_missing_directory_returns_empty_report(self, tmp_path: Path) -> None:
        monitor = DataQualityMonitor(root=str(tmp_path / "nonexistent"))
        report = monitor.run_checks(timeframe="1m")
        assert report.total_symbols == 0
        assert report.total_candles == 0
        assert len(report.symbol_reports) == 0

    def test_empty_parquet_returns_empty_report(self, tmp_path: Path) -> None:
        # Write an empty DataFrame
        _write_parquet(
            tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=EMPTY" / "data.parquet",
            pd.DataFrame(columns=["timestamp", "symbol", "open", "high", "low", "close", "volume"]),
        )
        _init_catalog(tmp_path / "catalog.duckdb")

        monitor = DataQualityMonitor(root=str(tmp_path))
        report = monitor.run_checks(timeframe="1m")
        # Empty data → 0 candles
        assert report.total_candles == 0 or report.total_symbols == 0

    def test_multi_symbol_report_structure(self, tmp_path: Path) -> None:
        """Verify each symbol gets its own SymbolQuality with all metrics."""
        for sym in ["AAA", "BBB", "CCC"]:
            df = _make_ohlcv_df(n=100, symbol=sym)
            _write_parquet(
                tmp_path / "equities" / "candles" / "timeframe=1m"
                / f"symbol={sym}" / "data.parquet",
                df,
            )
        _init_catalog(tmp_path / "catalog.duckdb")

        monitor = DataQualityMonitor(root=str(tmp_path))
        report = monitor.run_checks(timeframe="1m")

        assert report.total_symbols == 3
        assert len(report.symbol_reports) == 3
        symbols = {sq.symbol for sq in report.symbol_reports}
        assert symbols == {"AAA", "BBB", "CCC"}

        # Each symbol should have freshness, completeness, zero_volume, ohlc_integrity
        for sq in report.symbol_reports:
            metric_names = {m.name for m in sq.metrics}
            assert "freshness" in metric_names
            assert "completeness" in metric_names
            assert "zero_volume" in metric_names
            assert "ohlc_integrity" in metric_names

    def test_summary_metrics_populated(self, tmp_path: Path) -> None:
        # Use 375 candles = 1 full trading day of 1m data so completeness passes
        df = _make_ohlcv_df(n=375, symbol="TEST")
        _write_parquet(
            tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=TEST" / "data.parquet",
            df,
        )
        _init_catalog(tmp_path / "catalog.duckdb")

        monitor = DataQualityMonitor(root=str(tmp_path))
        report = monitor.run_checks(timeframe="1m")

        assert len(report.summary_metrics) > 0
        metric_names = {m.name for m in report.summary_metrics}
        assert "health_score" in metric_names
        assert report.health_score > 0

    def test_print_summary_does_not_raise(self, tmp_path: Path) -> None:
        df = _make_ohlcv_df(n=100, symbol="TEST")
        _write_parquet(
            tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=TEST" / "data.parquet",
            df,
        )
        _init_catalog(tmp_path / "catalog.duckdb")

        monitor = DataQualityMonitor(root=str(tmp_path))
        report = monitor.run_checks(timeframe="1m")
        # Should not raise
        monitor.print_summary(report)
