"""Tests for DuckDB analytics views."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from analytics.views.base import BaseViews
from analytics.views.features import FeatureViews
from analytics.views.manager import ViewManager
from analytics.views.quality import QualityViews
from analytics.views.scanner import ScannerViews
from analytics.views.validator import PointInTimeValidator


@pytest.fixture
def conn(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    """Create a temporary DuckDB connection for testing."""
    db_path = tmp_path / "test_views.duckdb"
    c = duckdb.connect(str(db_path))

    # Create minimal test data
    c.execute("""
        CREATE TABLE test_candles AS
        SELECT * FROM (VALUES
            (TIMESTAMP '2026-01-01 09:15:00', 'RELIANCE', 100.0, 105.0, 99.0, 103.0, 1000, 0),
            (TIMESTAMP '2026-01-01 09:16:00', 'RELIANCE', 103.0, 106.0, 102.0, 104.0, 1200, 0),
            (TIMESTAMP '2026-01-01 09:17:00', 'RELIANCE', 104.0, 107.0, 103.0, 105.0, 1100, 0),
            (TIMESTAMP '2026-01-01 09:15:00', 'INFY', 200.0, 205.0, 199.0, 203.0, 800, 0),
            (TIMESTAMP '2026-01-01 09:16:00', 'INFY', 203.0, 206.0, 202.0, 204.0, 900, 0),
            (TIMESTAMP '2026-01-01 09:17:00', 'INFY', 204.0, 207.0, 203.0, 205.0, 850, 0)
        ) AS t(timestamp, symbol, open, high, low, close, volume, oi)
    """)

    # Create view pointing to test data
    c.execute("""
        CREATE OR REPLACE VIEW v_candles_1m AS
        SELECT * FROM test_candles
    """)

    # Create materialized tables for intraday tests
    c.execute("""
        CREATE TABLE m_intraday AS
        SELECT * FROM test_candles
    """)

    c.execute("""
        CREATE TABLE m_recent_daily AS
        SELECT
            CAST(timestamp AS DATE) as trade_date,
            symbol,
            LAST(close ORDER BY timestamp) as close,
            LAST(close ORDER BY timestamp) as sma_20,
            LAST(close ORDER BY timestamp) as sma_50,
            0.0 as close_5d,
            0.0 as close_10d,
            0.0 as close_20d,
            1000.0 as avg_volume_20
        FROM test_candles
        GROUP BY CAST(timestamp AS DATE), symbol
    """)

    c.execute("""
        CREATE TABLE m_symbol_snapshot AS
        SELECT
            symbol,
            LAST(timestamp ORDER BY timestamp) as last_ts,
            LAST(close ORDER BY timestamp) as close,
            LAST(high ORDER BY timestamp) as high,
            LAST(low ORDER BY timestamp) as low,
            LAST(open ORDER BY timestamp) as open,
            LAST(volume ORDER BY timestamp) as volume,
            COUNT(*) as bars_today,
            MAX(high) as day_high,
            MIN(low) as day_low,
            FIRST(close ORDER BY timestamp) as day_open,
            LAST(close ORDER BY timestamp) as day_close,
            SUM(volume) as day_volume,
            LAST(close ORDER BY timestamp) as sma_20,
            LAST(close ORDER BY timestamp) as sma_50,
            0.0 as close_5d,
            0.0 as close_10d,
            0.0 as close_20d,
            0.0 as roc_5,
            0.0 as roc_10,
            0.0 as roc_20,
            'Neutral' as trend,
            1.0 as relative_volume
        FROM test_candles
        GROUP BY symbol
    """)

    c.execute("""
        CREATE TABLE m_intraday_snapshot AS
        SELECT
            symbol,
            close as ltp,
            day_open,
            day_high,
            day_low,
            day_close,
            day_volume,
            bars_today,
            sma_20,
            sma_50,
            roc_5,
            roc_10,
            roc_20,
            trend,
            relative_volume,
            close_5d,
            close_10d,
            close_20d,
            50.0 as rsi_approx,
            1.0 as atr_approx,
            0.0 as intraday_score,
            'NEUTRAL' as signal
        FROM m_symbol_snapshot
    """)

    yield c
    c.close()


class TestBaseViews:
    def test_create_daily_summary(self, conn: duckdb.DuckDBPyConnection) -> None:
        views = BaseViews()
        views._create_daily_summary(conn)
        result = conn.execute("SELECT COUNT(*) FROM v_daily_summary").fetchone()
        assert result[0] == 2  # RELIANCE and INFY

    def test_create_latest_candle(self, conn: duckdb.DuckDBPyConnection) -> None:
        views = BaseViews()
        views._create_latest_candle(conn)
        result = conn.execute("SELECT COUNT(*) FROM v_latest_candle").fetchone()
        assert result[0] == 2


class TestFeatureViews:
    def test_create_atr(self, conn: duckdb.DuckDBPyConnection) -> None:
        views = FeatureViews()
        views._create_atr(conn)
        result = conn.execute("SELECT COUNT(*) FROM v_feature_atr").fetchone()
        assert result[0] > 0

    def test_create_volume(self, conn: duckdb.DuckDBPyConnection) -> None:
        views = FeatureViews()
        views._create_volume(conn)
        result = conn.execute("SELECT COUNT(*) FROM v_feature_volume").fetchone()
        assert result[0] > 0

    def test_create_rsi(self, conn: duckdb.DuckDBPyConnection) -> None:
        views = FeatureViews()
        views._create_rsi(conn)
        result = conn.execute("SELECT COUNT(*) FROM v_feature_rsi").fetchone()
        assert result[0] > 0

    def test_create_momentum(self, conn: duckdb.DuckDBPyConnection) -> None:
        views = FeatureViews()
        views._create_momentum(conn)
        result = conn.execute("SELECT COUNT(*) FROM v_feature_momentum").fetchone()
        assert result[0] > 0


class TestScannerViews:
    def test_create_intraday_vwap(self, conn: duckdb.DuckDBPyConnection) -> None:
        views = ScannerViews()
        views._create_intraday_vwap(conn)
        result = conn.execute("SELECT COUNT(*) FROM v_intraday_vwap").fetchone()
        assert result[0] > 0

    def test_create_intraday_rsi(self, conn: duckdb.DuckDBPyConnection) -> None:
        views = ScannerViews()
        views._create_intraday_rsi(conn)
        result = conn.execute("SELECT COUNT(*) FROM v_intraday_rsi").fetchone()
        assert result[0] > 0

    def test_create_intraday_atr(self, conn: duckdb.DuckDBPyConnection) -> None:
        views = ScannerViews()
        views._create_intraday_atr(conn)
        result = conn.execute("SELECT COUNT(*) FROM v_intraday_atr").fetchone()
        assert result[0] > 0

    def test_create_top3_candidates(self, conn: duckdb.DuckDBPyConnection) -> None:
        views = ScannerViews()
        views._create_intraday_vwap(conn)
        views._create_intraday_rsi(conn)
        views._create_intraday_atr(conn)
        views._create_intraday_snapshot(conn)
        views._create_top3_candidates(conn)
        result = conn.execute("SELECT COUNT(*) FROM v_top3_candidates").fetchone()
        assert result[0] >= 0


class TestQualityViews:
    def test_create_duplicate_candles(self, conn: duckdb.DuckDBPyConnection) -> None:
        # Create materialized tables that quality views now depend on
        conn.execute(
            "CREATE TABLE IF NOT EXISTS m_duplicate_candles (symbol VARCHAR, timestamp TIMESTAMP, duplicate_count BIGINT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS m_missing_candles (symbol VARCHAR, trade_date DATE, minute_count BIGINT)"
        )
        views = QualityViews()
        views._create_duplicate_candles(conn)
        result = conn.execute("SELECT COUNT(*) FROM v_duplicate_candles").fetchone()
        assert result[0] == 0  # No duplicates in test data


class TestPointInTimeValidator:
    def test_validate_candles(self, conn: duckdb.DuckDBPyConnection) -> None:
        validator = PointInTimeValidator(conn)
        report = validator.validate_view("v_candles_1m")
        assert report.view_name == "v_candles_1m"

    def test_validate_nonexistent_view(self, conn: duckdb.DuckDBPyConnection) -> None:
        validator = PointInTimeValidator(conn)
        report = validator.validate_view("nonexistent_view")
        assert not report.is_valid
        assert len(report.issues) > 0


class TestViewManager:
    def test_list_views(self, tmp_path: Path) -> None:
        vm = ViewManager(catalog_path=tmp_path / "test.duckdb")
        try:
            views = vm.list_views()
            assert isinstance(views, list)
        finally:
            vm.close()

    def test_view_count(self, tmp_path: Path) -> None:
        vm = ViewManager(catalog_path=tmp_path / "test.duckdb")
        try:
            count = vm.view_count()
            assert isinstance(count, int)
        finally:
            vm.close()

    def test_materialize_creates_versioned_snapshot(self, tmp_path: Path) -> None:
        from analytics.views.manager import MATERIALIZED_DIR

        vm = ViewManager(catalog_path=tmp_path / "test.duckdb")
        try:
            vm.conn.execute("CREATE TABLE test_data AS SELECT 1 AS x, 'A' AS y")
            vm.materialize("test_table", "SELECT * FROM test_data")
            vm.register_materialized("test_table")

            rows = vm.conn.execute("SELECT * FROM test_table").fetchall()
            assert len(rows) == 1
            assert rows[0][0] == 1

            # A version directory and latest registry should exist.
            version_dir = MATERIALIZED_DIR / "versions" / "test_table"
            assert version_dir.exists()
            assert (version_dir / "latest.json").exists()
        finally:
            vm.drop_materialized("test_table")
            vm.close()
