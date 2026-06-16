"""Tests for datalake.quality — DataQualityEngine."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from datalake.quality import DataQualityEngine, QualityReport


def _write_parquet(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _make_canonical_df(n: int = 100, symbol: str = "TEST", start: str = "2026-01-01") -> pd.DataFrame:
    """Create a canonical DataFrame with valid OHLCV data."""
    np.random.seed(42)
    dates = pd.date_range(start, periods=n, freq="1min")
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "timestamp": dates,
        "symbol": symbol,
        "exchange": "NSE",
        "open": close + np.random.randn(n) * 0.2,
        "high": close + np.abs(np.random.randn(n) * 0.5),
        "low": close - np.abs(np.random.randn(n) * 0.5),
        "close": close,
        "volume": np.random.randint(1000, 10000, n),
        "oi": np.zeros(n, dtype=np.int64),
    })


class TestQualityReport:
    def test_summary_output(self) -> None:
        report = QualityReport(symbol="TEST", total_rows=1000, status="OK")
        output = report.summary()
        assert "TEST" in output
        assert "1,000" in output
        assert "OK" in output

    def test_summary_with_issues(self) -> None:
        report = QualityReport(symbol="TEST", issues=["Missing candles", "Duplicates"])
        output = report.summary()
        assert "Missing candles" in output
        assert "Duplicates" in output


class TestCheckMissingSymbol:
    def test_missing_symbol(self, tmp_path: Path) -> None:
        engine = DataQualityEngine(root=str(tmp_path))
        report = engine.check("NONEXISTENT")
        assert report.status == "MISSING"
        assert report.total_rows == 0
        assert len(report.issues) > 0


class TestCheckValidSymbol:
    def test_valid_symbol(self, tmp_path: Path) -> None:
        df = _make_canonical_df(n=500)
        parquet_path = tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=TEST" / "data.parquet"
        _write_parquet(parquet_path, df)

        engine = DataQualityEngine(root=str(tmp_path))
        report = engine.check("TEST")

        assert report.status == "OK"
        assert report.total_rows == 500
        assert report.min_date is not None
        assert report.max_date is not None

    def test_empty_file(self, tmp_path: Path) -> None:
        parquet_path = tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=TEST" / "data.parquet"
        _write_parquet(parquet_path, pd.DataFrame())

        engine = DataQualityEngine(root=str(tmp_path))
        report = engine.check("TEST")
        assert report.status == "EMPTY"


class TestCheckDuplicates:
    def test_duplicate_timestamps(self, tmp_path: Path) -> None:
        df = _make_canonical_df(n=100)
        # Add duplicates
        dup = df.iloc[:5]
        df = pd.concat([df, dup], ignore_index=True)

        parquet_path = tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=TEST" / "data.parquet"
        _write_parquet(parquet_path, df)

        engine = DataQualityEngine(root=str(tmp_path))
        report = engine.check("TEST")

        assert report.duplicate_candles == 5
        assert report.status == "WARNING"


class TestCheckOHLConsistency:
    def test_high_less_than_low(self, tmp_path: Path) -> None:
        df = _make_canonical_df(n=100)
        # Corrupt: make high < low
        df.loc[0, "high"] = 50.0
        df.loc[0, "low"] = 200.0

        parquet_path = tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=TEST" / "data.parquet"
        _write_parquet(parquet_path, df)

        engine = DataQualityEngine(root=str(tmp_path))
        report = engine.check("TEST")

        assert any("high < low" in issue for issue in report.issues)


class TestCheckZeroVolume:
    def test_zero_volume_rows(self, tmp_path: Path) -> None:
        df = _make_canonical_df(n=100)
        df.loc[0, "volume"] = 0
        df.loc[1, "volume"] = 0

        parquet_path = tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=TEST" / "data.parquet"
        _write_parquet(parquet_path, df)

        engine = DataQualityEngine(root=str(tmp_path))
        report = engine.check("TEST")

        assert any("zero volume" in issue for issue in report.issues)


class TestCheckUniverse:
    def test_check_universe(self, tmp_path: Path) -> None:
        # Create universe CSV
        universe_dir = tmp_path / "data" / "universes"
        universe_dir.mkdir(parents=True)
        csv_path = universe_dir / "TEST5.csv"
        pd.DataFrame({"symbol": ["SYM_A", "SYM_B"]}).to_csv(csv_path, index=False)

        # Create data for both symbols
        for sym in ["SYM_A", "SYM_B"]:
            df = _make_canonical_df(n=100, symbol=sym)
            parquet_path = tmp_path / "equities" / "candles" / "timeframe=1m" / f"symbol={sym}" / "data.parquet"
            _write_parquet(parquet_path, df)

        engine = DataQualityEngine(root=str(tmp_path))
        # Monkey-patch UNIVERSE_FILES to use our test CSV
        import datalake.quality as q
        from datalake.schema import UNIVERSE_FILES
        UNIVERSE_FILES["TEST5"] = str(csv_path)

        reports = engine.check_universe("TEST5")
        assert len(reports) == 2
        statuses = {r.symbol: r.status for r in reports}
        assert statuses["SYM_A"] == "OK"
        assert statuses["SYM_B"] == "OK"


class TestCheckWithCatalog:
    def test_records_to_catalog(self, tmp_path: Path) -> None:
        from datalake.catalog import DataCatalog

        df = _make_canonical_df(n=100)
        parquet_path = tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=TEST" / "data.parquet"
        _write_parquet(parquet_path, df)

        catalog = DataCatalog(root=str(tmp_path))
        engine = DataQualityEngine(root=str(tmp_path), catalog=catalog)
        engine.check("TEST")

        # Should have recorded quality in catalog
        result = catalog.conn.execute(
            "SELECT * FROM data_quality WHERE symbol = 'TEST'"
        ).fetchone()
        assert result is not None
        catalog.close()
