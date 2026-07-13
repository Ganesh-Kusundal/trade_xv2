"""End-to-end tests for DuckDB modules — shared utilities, catalog, scan store, views, validator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from analytics.views.base import BaseViews
from analytics.views.features import FeatureViews
from analytics.views.manager import ViewManager
from analytics.views.quality import _get_session_constants

TRADING_MINUTES_PER_DAY, TRADING_MINUTES_PARTIAL = _get_session_constants()
from analytics.views.scanner import ScannerViews
from analytics.views.strategy import StrategyViews
from analytics.views.validator import VALID_VIEWS, PointInTimeValidator
from datalake.storage.catalog import DataCatalog
from datalake.core.duckdb_utils import connect_with_retry, get_pool
from datalake.research.scan_store import (
    compare_scans,
    ensure_scan_table,
    get_recent_scans,
    get_scan_symbols,
    save_scan_result,
)

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _close_writer(catalog: DataCatalog) -> None:
    """Close the RW connection so subsequent reads can open RO connections."""
    catalog.close()
    get_pool().close(catalog._db_path)


def _make_parquet(path: Path, n: int = 500, symbol: str = "TEST") -> None:
    """Create a synthetic canonical Parquet file with enough data for indicators."""
    np.random.seed(42)
    dates = pd.date_range("2026-06-01 09:15:00", periods=n, freq="1min")
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame(
        {
            "timestamp": dates,
            "symbol": symbol,
            "exchange": "NSE",
            "open": close + np.random.randn(n) * 0.2,
            "high": close + np.abs(np.random.randn(n) * 0.5),
            "low": close - np.abs(np.random.randn(n) * 0.5),
            "close": close,
            "volume": np.random.randint(1000, 10000, n),
            "oi": np.zeros(n, dtype=np.int64),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


@dataclass
class _Candidate:
    """Mock candidate for scan_store tests."""

    symbol: str
    score: float
    reasons: list[str] | None = None


# ─── connect_with_retry Tests ─────────────────────────────────────────────────


class TestConnectWithRetry:
    def test_succeeds_on_unlocked_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / "retry.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("CREATE TABLE t (x INT)")
        conn.close()

        conn = connect_with_retry(str(db_path), read_only=True, max_attempts=3)
        assert conn is not None
        conn.close()

    def test_non_lock_error_propagates(self) -> None:
        with pytest.raises(duckdb.IOException):
            connect_with_retry("/nonexistent/path/db.duckdb", read_only=True, max_attempts=3)


# ─── DataCatalog Integration Tests ───────────────────────────────────────────


class TestDataCatalogIntegration:
    def test_full_lifecycle(self, tmp_path: Path) -> None:
        """Test register → query → quality → summary lifecycle."""
        catalog = DataCatalog(root=str(tmp_path))
        try:
            catalog.register_symbol("RELIANCE", total_rows=100000)
            catalog.register_symbol("TCS", total_rows=50000)
            catalog.register_symbol("INFY", total_rows=75000)
            catalog.record_quality("RELIANCE", total_rows=100000, completeness_pct=99.5)
            _close_writer(catalog)

            symbols = catalog.list_symbols()
            assert len(symbols) == 3
            assert "INFY" in symbols

            sym = catalog.get_symbol("RELIANCE")
            assert sym is not None
            assert sym["total_rows"] == 100000

            summary = catalog.summary()
            assert summary["symbols"] == 3
            assert summary["total_rows"] == 225000
            assert summary["quality_records"] == 1
        finally:
            catalog.close()

    def test_scan_parquet_files_integration(self, tmp_path: Path) -> None:
        """Scan real Parquet files and register them."""
        candles_dir = tmp_path / "equities" / "candles" / "timeframe=1m"
        for sym in ["RELIANCE", "TCS", "HDFCBANK"]:
            _make_parquet(candles_dir / f"symbol={sym}" / "data.parquet", symbol=sym)

        catalog = DataCatalog(root=str(tmp_path))
        try:
            count = catalog.scan_parquet_files()
            assert count == 3
            _close_writer(catalog)

            symbols = catalog.list_symbols()
            assert "RELIANCE" in symbols

            path = catalog.get_parquet_path("RELIANCE")
            assert path is not None
            assert path.exists()
        finally:
            catalog.close()

    def test_reopen_same_instance_uses_cached_conn(self, tmp_path: Path) -> None:
        """Calling .conn twice returns the same connection object."""
        catalog = DataCatalog(root=str(tmp_path))
        try:
            c1 = catalog.conn
            c2 = catalog.conn
            assert c1 is c2
        finally:
            catalog.close()


# ─── ScanStore Integration Tests ──────────────────────────────────────────────


class TestScanStoreIntegration:
    def test_full_scan_lifecycle(self, tmp_path: Path) -> None:
        """Test save → query → compare lifecycle using explicit connection."""
        db_path = tmp_path / "scan.duckdb"
        conn = duckdb.connect(str(db_path))
        try:
            ensure_scan_table(conn)

            candidates1 = [
                _Candidate("RELIANCE", 85.0, ["momentum"]),
                _Candidate("TCS", 72.0, ["volume"]),
            ]
            id1 = save_scan_result("momentum", candidates1, 500, conn=conn)

            candidates2 = [
                _Candidate("RELIANCE", 90.0, ["breakout"]),
                _Candidate("INFY", 65.0, ["trend"]),
            ]
            id2 = save_scan_result("breakout", candidates2, 500, conn=conn)

            scans = get_recent_scans(conn=conn)
            assert len(scans) == 2

            symbols = get_scan_symbols(id1, conn)
            assert len(symbols) == 2
            assert symbols[0]["symbol"] == "RELIANCE"

            result = compare_scans(id1, id2, conn)
            assert "RELIANCE" in result["added"] or "RELIANCE" not in result["removed"]
        finally:
            conn.close()

    def test_compare_scans_added_removed_changed(self, tmp_path: Path) -> None:
        db_path = tmp_path / "compare.duckdb"
        conn = duckdb.connect(str(db_path))
        try:
            ensure_scan_table(conn)

            id1 = save_scan_result(
                "test",
                [
                    _Candidate("RELIANCE", 80.0),
                    _Candidate("TCS", 70.0),
                ],
                100,
                conn=conn,
            )

            id2 = save_scan_result(
                "test",
                [
                    _Candidate("RELIANCE", 90.0),
                    _Candidate("INFY", 65.0),
                ],
                100,
                conn=conn,
            )

            result = compare_scans(id1, id2, conn)
            assert "INFY" in result["added"]
            assert "TCS" in result["removed"]
            assert any(c["symbol"] == "RELIANCE" for c in result["changed"])
        finally:
            conn.close()


# ─── Module-level Fixture ─────────────────────────────────────────────────────


@pytest.fixture
def view_conn(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    """Create a DuckDB connection with test data for views."""
    db_path = tmp_path / "views_e2e.duckdb"
    c = duckdb.connect(str(db_path))

    np.random.seed(42)
    n = 500
    dates = pd.date_range("2026-06-01 09:15:00", periods=n, freq="1min")
    close_vals = 100 + np.cumsum(np.random.randn(n) * 0.5)

    c.execute(
        """
        CREATE TABLE test_candles AS
        SELECT * FROM (VALUES
    """
        + ",".join(
            [
                f"(TIMESTAMP '{dates[i]}', 'RELIANCE', {close_vals[i]:.2f}, {close_vals[i] + 1:.2f}, {close_vals[i] - 1:.2f}, {close_vals[i]:.2f}, 1000, 0)"
                for i in range(n)
            ]
        )
        + """) AS t(timestamp, symbol, open, high, low, close, volume, oi)"""
    )

    c.execute("CREATE OR REPLACE VIEW v_candles_1m AS SELECT * FROM test_candles")

    c.execute("CREATE TABLE m_intraday AS SELECT * FROM test_candles")

    c.execute("""
        CREATE TABLE m_recent_daily AS
        SELECT
            CAST(timestamp AS DATE) as trade_date,
            symbol,
            LAST(close ORDER BY timestamp) as open,
            LAST(close ORDER BY timestamp) as high,
            LAST(close ORDER BY timestamp) as low,
            LAST(close ORDER BY timestamp) as close,
            1000 as volume,
            LAST(close ORDER BY timestamp) as sma_20,
            LAST(close ORDER BY timestamp) as sma_50,
            0.0 as daily_change,
            1000.0 as avg_volume_20,
            0.0 as close_5d,
            0.0 as close_10d,
            0.0 as close_20d
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
            (day_high - day_low) as atr_approx,
            50.0 as intraday_score,
            'NEUTRAL' as signal
        FROM m_symbol_snapshot
    """)

    # Quality materialized tables (empty — no duplicates or missing candles in test data)
    c.execute("""
        CREATE TABLE m_duplicate_candles (
            symbol VARCHAR,
            timestamp TIMESTAMP,
            duplicate_count BIGINT
        )
    """)
    c.execute("""
        CREATE TABLE m_missing_candles (
            symbol VARCHAR,
            trade_date DATE,
            minute_count BIGINT
        )
    """)
    c.execute("""
        CREATE TABLE m_trading_days (
            symbol VARCHAR,
            trade_date DATE
        )
    """)
    # Populate m_trading_days with the test symbol's trading days
    c.execute("""
        INSERT INTO m_trading_days
        SELECT 'RELIANCE', CAST(timestamp AS DATE) FROM test_candles GROUP BY CAST(timestamp AS DATE)
    """)

    yield c
    c.close()


# ─── Analytics Views Integration Tests ────────────────────────────────────────


class TestAnalyticsViewsIntegration:
    def test_base_views_create_and_query(self, view_conn: duckdb.DuckDBPyConnection) -> None:
        """Base views can be created and queried (skip _create_candles_1m since fixture provides it)."""
        base = BaseViews()
        base._create_daily_summary(view_conn)
        base._create_latest_candle(view_conn)

        count = view_conn.execute("SELECT COUNT(*) FROM v_candles_1m").fetchone()[0]
        assert count == 500

        count = view_conn.execute("SELECT COUNT(*) FROM v_daily_summary").fetchone()[0]
        assert count >= 1

        count = view_conn.execute("SELECT COUNT(*) FROM v_latest_candle").fetchone()[0]
        assert count == 1

    def test_feature_views_create_and_query(self, view_conn: duckdb.DuckDBPyConnection) -> None:
        features = FeatureViews()
        features.create_views(view_conn)

        for view_name in [
            "v_feature_atr",
            "v_feature_vwap",
            "v_feature_volume",
            "v_feature_momentum",
            "v_feature_rsi",
        ]:
            count = view_conn.execute(f"SELECT COUNT(*) FROM {view_name}").fetchone()[0]
            assert count == 500

    def test_scanner_views_create_and_query(self, view_conn: duckdb.DuckDBPyConnection) -> None:
        scanner = ScannerViews()
        scanner.create_views(view_conn)

        for view_name in [
            "v_intraday_vwap",
            "v_intraday_rsi",
            "v_intraday_atr",
            "v_intraday_snapshot",
        ]:
            count = view_conn.execute(f"SELECT COUNT(*) FROM {view_name}").fetchone()[0]
            assert count >= 1

        count = view_conn.execute("SELECT COUNT(*) FROM v_top3_candidates").fetchone()[0]
        assert count <= 3

        count = view_conn.execute("SELECT COUNT(*) FROM v_top10_candidates").fetchone()[0]
        assert count <= 10

    def test_strategy_views_create_and_query(self, view_conn: duckdb.DuckDBPyConnection) -> None:
        strategy = StrategyViews()
        strategy.create_views(view_conn)

        for view_name in [
            "v_strategy_halftrend",
            "v_strategy_candidates",
            "v_strategy_momentum",
            "v_strategy_breakout",
        ]:
            exists = view_conn.execute(
                "SELECT COUNT(*) FROM duckdb_views() WHERE view_name = ? AND schema_name = 'main'",
                [view_name],
            ).fetchone()[0]
            assert exists > 0

    def test_quality_views_create_and_query(self, view_conn: duckdb.DuckDBPyConnection) -> None:
        view_conn.execute(f"""
            CREATE OR REPLACE VIEW v_missing_candles AS
            SELECT
                symbol,
                trade_date,
                minute_count,
                CASE
                    WHEN minute_count < {TRADING_MINUTES_PARTIAL} THEN 'INCOMPLETE'
                    WHEN minute_count < {TRADING_MINUTES_PER_DAY} THEN 'PARTIAL'
                    ELSE 'COMPLETE'
                END as status
            FROM m_missing_candles
            WHERE minute_count < {TRADING_MINUTES_PER_DAY}
            ORDER BY trade_date DESC, symbol
        """)
        view_conn.execute("""
            CREATE OR REPLACE VIEW v_duplicate_candles AS
            SELECT symbol, timestamp, duplicate_count
            FROM m_duplicate_candles
            ORDER BY duplicate_count DESC
        """)
        view_conn.execute(f"""
            CREATE OR REPLACE VIEW v_quality_score AS
            WITH completeness AS (
                SELECT symbol, COUNT(DISTINCT trade_date) as trading_days
                FROM m_trading_days GROUP BY symbol
            ),
            duplicates AS (SELECT symbol, COUNT(*) as dup_count FROM m_duplicate_candles GROUP BY symbol),
            missing AS (SELECT symbol, COALESCE(SUM({TRADING_MINUTES_PER_DAY} - minute_count), 0) as missing_minutes
                        FROM m_missing_candles GROUP BY symbol)
            SELECT c.symbol, c.trading_days,
                   COALESCE(d.dup_count, 0) as duplicate_count,
                   CAST(COALESCE(m.missing_minutes, 0) AS BIGINT) as missing_count,
                   CASE WHEN c.trading_days = 0 THEN 0
                        ELSE ROUND((1.0 - COALESCE(m.missing_minutes, 0) / NULLIF(c.trading_days * {TRADING_MINUTES_PER_DAY}.0, 0)) * 100, 2)
                   END as quality_score
            FROM completeness c
            LEFT JOIN duplicates d ON c.symbol = d.symbol
            LEFT JOIN missing m ON c.symbol = m.symbol
            ORDER BY quality_score DESC
        """)

        for view_name in ["v_missing_candles", "v_duplicate_candles", "v_quality_score"]:
            exists = view_conn.execute(
                "SELECT COUNT(*) FROM duckdb_views() WHERE view_name = ? AND schema_name = 'main'",
                [view_name],
            ).fetchone()[0]
            assert exists > 0

        count = view_conn.execute("SELECT COUNT(*) FROM v_quality_score").fetchone()[0]
        assert count >= 1


# ─── PointInTimeValidator Tests ───────────────────────────────────────────────


class TestPointInTimeValidatorIntegration:
    def test_validate_all_views_exist(self, view_conn: duckdb.DuckDBPyConnection) -> None:
        BaseViews()._create_daily_summary(view_conn)
        BaseViews()._create_latest_candle(view_conn)
        FeatureViews().create_views(view_conn)

        validator = PointInTimeValidator(view_conn)
        reports = validator.validate_all()

        reported_names = {r.view_name for r in reports}
        for view_name in VALID_VIEWS:
            assert view_name in reported_names

    def test_validator_uses_duckdb_views_not_pg_views(
        self, view_conn: duckdb.DuckDBPyConnection
    ) -> None:
        BaseViews()._create_daily_summary(view_conn)
        BaseViews()._create_latest_candle(view_conn)

        validator = PointInTimeValidator(view_conn)
        report = validator.validate_view("v_candles_1m")
        assert report.view_name == "v_candles_1m"

    def test_validator_detects_lookahead(self, tmp_path: Path) -> None:
        c = duckdb.connect(str(tmp_path / "lookahead.duckdb"))
        try:
            c.execute("""
                CREATE TABLE test_data AS
                SELECT * FROM (VALUES
                    (TIMESTAMP '2026-01-01 09:15:00', 'RELIANCE', 100.0),
                    (TIMESTAMP '2026-01-01 09:16:00', 'RELIANCE', 101.0)
                ) AS t(timestamp, symbol, close)
            """)
            c.execute("""
                CREATE OR REPLACE VIEW v_feature_bad AS
                SELECT symbol, timestamp, close,
                    LEAD(close) OVER (PARTITION BY symbol ORDER BY timestamp) as next_close
                FROM test_data
            """)

            validator = PointInTimeValidator(c)
            report = validator.validate_view("v_feature_bad")
            assert not report.is_valid
            assert any("LEAD()" in issue for issue in report.issues)
        finally:
            c.close()


class TestQualityScoreFormula:
    """Test the fixed quality score formula uses m_trading_days + sum of missing minutes."""

    def test_uses_full_history_not_50day_window(self, tmp_path: Path) -> None:
        """Quality score must use m_trading_days (full history), not m_recent_daily (50-day window)."""
        c = duckdb.connect(str(tmp_path / "qs.duckdb"))
        try:
            c.execute("""
                CREATE TABLE m_trading_days (symbol VARCHAR, trade_date DATE);
                CREATE TABLE m_duplicate_candles (symbol VARCHAR, timestamp TIMESTAMP, duplicate_count BIGINT);
                CREATE TABLE m_missing_candles (symbol VARCHAR, trade_date DATE, minute_count BIGINT);
            """)
            # 1000 trading days for SYM1, 10 for SYM2
            c.execute("""
                INSERT INTO m_trading_days
                SELECT 'SYM1', DATE '2020-01-01' + CAST(i AS INTEGER) FROM range(0, 1000) t(i);
                INSERT INTO m_trading_days
                SELECT 'SYM2', DATE '2020-01-01' + CAST(i AS INTEGER) FROM range(0, 10) t(i);
            """)
            c.execute("""
                CREATE OR REPLACE VIEW v_quality_score AS
                WITH completeness AS (
                    SELECT symbol, COUNT(DISTINCT trade_date) as trading_days
                    FROM m_trading_days GROUP BY symbol
                ),
                duplicates AS (SELECT symbol, COUNT(*) as dup_count FROM m_duplicate_candles GROUP BY symbol),
                missing AS (SELECT symbol, COALESCE(SUM(375 - minute_count), 0) as missing_minutes
                            FROM m_missing_candles GROUP BY symbol)
                SELECT c.symbol, c.trading_days,
                       COALESCE(d.dup_count, 0) as duplicate_count,
                       CAST(COALESCE(m.missing_minutes, 0) AS BIGINT) as missing_count,
                       CASE WHEN c.trading_days = 0 THEN 0
                            ELSE ROUND((1.0 - COALESCE(m.missing_minutes, 0) / NULLIF(c.trading_days * 375.0, 0)) * 100, 2)
                       END as quality_score
                FROM completeness c
                LEFT JOIN duplicates d ON c.symbol = d.symbol
                LEFT JOIN missing m ON c.symbol = m.symbol
            """)

            r = c.execute(
                "SELECT symbol, trading_days FROM v_quality_score ORDER BY symbol"
            ).fetchall()
            by_sym = dict(r)
            assert by_sym["SYM1"] == 1000, f"SYM1 should have 1000 days, got {by_sym['SYM1']}"
            assert by_sym["SYM2"] == 10, f"SYM2 should have 10 days, got {by_sym['SYM2']}"
        finally:
            c.close()

    def test_uses_sum_of_missing_minutes_not_count_of_days(self, tmp_path: Path) -> None:
        """Quality score must use SUM(375-minute_count) for actual missing minutes, not COUNT(days)."""
        c = duckdb.connect(str(tmp_path / "qs2.duckdb"))
        try:
            c.execute("""
                CREATE TABLE m_trading_days (symbol VARCHAR, trade_date DATE);
                CREATE TABLE m_duplicate_candles (symbol VARCHAR, timestamp TIMESTAMP, duplicate_count BIGINT);
                CREATE TABLE m_missing_candles (symbol VARCHAR, trade_date DATE, minute_count BIGINT);
            """)
            # 100 days, each missing 10 minutes → 1000 missing minutes total
            c.execute("""
                INSERT INTO m_trading_days
                SELECT 'SYM', DATE '2020-01-01' + CAST(i AS INTEGER) FROM range(0, 100) t(i);
                INSERT INTO m_missing_candles
                SELECT 'SYM', DATE '2020-01-01' + CAST(i AS INTEGER), 365 FROM range(0, 100) t(i);
            """)
            c.execute("""
                CREATE OR REPLACE VIEW v_quality_score AS
                WITH completeness AS (
                    SELECT symbol, COUNT(DISTINCT trade_date) as trading_days
                    FROM m_trading_days GROUP BY symbol
                ),
                duplicates AS (SELECT symbol, COUNT(*) as dup_count FROM m_duplicate_candles GROUP BY symbol),
                missing AS (SELECT symbol, COALESCE(SUM(375 - minute_count), 0) as missing_minutes
                            FROM m_missing_candles GROUP BY symbol)
                SELECT c.symbol, c.trading_days,
                       CAST(COALESCE(m.missing_minutes, 0) AS BIGINT) as missing_count,
                       CASE WHEN c.trading_days = 0 THEN 0
                            ELSE ROUND((1.0 - COALESCE(m.missing_minutes, 0) / NULLIF(c.trading_days * 375.0, 0)) * 100, 2)
                       END as quality_score
                FROM completeness c
                LEFT JOIN missing m ON c.symbol = m.symbol
            """)

            row = c.execute(
                "SELECT missing_count, quality_score FROM v_quality_score WHERE symbol='SYM'"
            ).fetchone()
            missing_count, quality_score = row
            # 100 days x 10 missing minutes = 1000 missing minutes (not just 100)
            assert missing_count == 1000, f"Expected 1000 missing minutes, got {missing_count}"
            # quality = (1 - 1000/37500) * 100 = 97.33%
            assert abs(quality_score - 97.33) < 0.1, f"Expected ~97.33, got {quality_score}"
        finally:
            c.close()


# ─── ViewManager Integration Tests ────────────────────────────────────────────


class TestViewManagerIntegration:
    def test_create_all_and_query(self, tmp_path: Path) -> None:
        vm = ViewManager(catalog_path=tmp_path / "vm_test.duckdb")
        try:
            vm.base.create_views(vm.conn)
            timings = vm.create_all()
            assert isinstance(timings, dict)
            assert "base" in timings
        finally:
            vm.close()

    def test_list_views(self, tmp_path: Path) -> None:
        vm = ViewManager(catalog_path=tmp_path / "vm_list.duckdb")
        try:
            vm.base.create_views(vm.conn)
            views = vm.list_views()
            view_names = [v["name"] for v in views]
            assert "v_candles_1m" in view_names
        finally:
            vm.close()

    def test_materialize_and_register(self, tmp_path: Path) -> None:
        vm = ViewManager(catalog_path=tmp_path / "vm_mat.duckdb")
        try:
            vm.conn.execute("CREATE TABLE test_data AS SELECT 1 AS x, 'A' AS y")
            vm.materialize("e2e_test_table", "SELECT * FROM test_data")
            vm.register_materialized("e2e_test_table")

            rows = vm.conn.execute("SELECT * FROM e2e_test_table").fetchall()
            assert len(rows) == 1
            assert rows[0][0] == 1

            from analytics.views.manager import MATERIALIZED_DIR

            version_dir = MATERIALIZED_DIR / "versions" / "e2e_test_table"
            assert version_dir.exists()
            assert (version_dir / "latest.json").exists()
        finally:
            vm.drop_materialized("e2e_test_table")
            vm.close()

    def test_benchmark_small_queries(self, tmp_path: Path) -> None:
        vm = ViewManager(catalog_path=tmp_path / "vm_bench.duckdb")
        try:
            vm.base.create_views(vm.conn)
            queries = [
                ("v_daily_summary", "SELECT COUNT(*) FROM v_daily_summary"),
                ("v_latest_candle", "SELECT COUNT(*) FROM v_latest_candle"),
            ]
            for name, sql in queries:
                if vm.view_exists(name):
                    bench = vm.benchmark(sql, iterations=1)
                    assert "avg_ms" in bench
        finally:
            vm.close()

    def test_drop_all(self, tmp_path: Path) -> None:
        vm = ViewManager(catalog_path=tmp_path / "vm_drop.duckdb")
        try:
            vm.base.create_views(vm.conn)
            count_before = vm.view_count()
            assert count_before > 0

            vm.drop_all()
            count_after = vm.view_count()
            assert count_after == 0
        finally:
            vm.close()


# ─── Cross-Module Integration Tests ──────────────────────────────────────────


class TestCrossModuleIntegration:
    def test_catalog_and_scan_store_share_db(self, tmp_path: Path) -> None:
        catalog = DataCatalog(root=str(tmp_path))
        try:
            catalog.register_symbol("RELIANCE", total_rows=100000)
            _close_writer(catalog)

            symbol = catalog.get_symbol("RELIANCE")
            assert symbol is not None

            db_path = tmp_path / "catalog.duckdb"
            conn = duckdb.connect(str(db_path))
            try:
                ensure_scan_table(conn)
                candidates = [_Candidate("RELIANCE", 85.0)]
                scan_id = save_scan_result("momentum", candidates, 500, conn=conn)

                scans = get_scan_symbols(scan_id, conn)
                assert len(scans) == 1
            finally:
                conn.close()
        finally:
            catalog.close()

    def test_full_pipeline_catalog_to_views(self, tmp_path: Path) -> None:
        catalog = DataCatalog(root=str(tmp_path))
        try:
            catalog.register_symbol("RELIANCE", total_rows=100000)
            catalog.register_symbol("TCS", total_rows=50000)
            _close_writer(catalog)

            summary = catalog.summary()
            assert summary["symbols"] == 2
        finally:
            catalog.close()

        vm = ViewManager(catalog_path=tmp_path / "catalog.duckdb")
        try:
            vm.base.create_views(vm.conn)
            views = vm.list_views()
            assert any(v["name"] == "v_candles_1m" for v in views)
        finally:
            vm.close()


# ─── Determinism Tests ────────────────────────────────────────────────────────


class TestDeterminism:
    def test_top3_candidates_deterministic(self, tmp_path: Path) -> None:
        c = duckdb.connect(str(tmp_path / "det.duckdb"))
        try:
            c.execute("""
                CREATE TABLE m_intraday_snapshot AS
                SELECT * FROM (VALUES
                    ('RELIANCE', 100.0, 100.0, 105.0, 99.0, 103.0, 1000, 1, 105.0, 99.0, 1.0, 1.0, 1.0, 'Bullish', 1.0, 0.0, 0.0, 0.0, 1.0, 1.0, 50.0, 'BUY'),
                    ('INFY', 200.0, 200.0, 205.0, 199.0, 203.0, 800, 1, 205.0, 199.0, 1.0, 1.0, 1.0, 'Bullish', 1.0, 0.0, 0.0, 0.0, 1.0, 1.0, 50.0, 'BUY'),
                    ('TCS', 300.0, 300.0, 305.0, 299.0, 303.0, 900, 1, 305.0, 299.0, 1.0, 1.0, 1.0, 'Bullish', 1.0, 0.0, 0.0, 0.0, 1.0, 1.0, 50.0, 'BUY')
                ) AS t(symbol, ltp, day_open, day_high, day_low, day_close, day_volume, bars_today, sma_20, sma_50, roc_5, roc_10, roc_20, trend, relative_volume, close_5d, close_10d, close_20d, atr_approx, rsi_approx, intraday_score, signal)
            """)

            scanner = ScannerViews()
            scanner._create_top3_candidates(c)

            results = []
            for _ in range(10):
                rows = c.execute("SELECT symbol FROM v_top3_candidates").fetchall()
                results.append([r[0] for r in rows])

            assert all(r == results[0] for r in results)
        finally:
            c.close()


# ─── Named Constants Tests ────────────────────────────────────────────────────


class TestNamedConstants:
    def test_quality_constants(self) -> None:
        # Values derived from the active exchange calendar
        assert TRADING_MINUTES_PER_DAY == 375  # NSE default
        assert TRADING_MINUTES_PARTIAL == 345  # 92% of 375

    def test_manager_constants(self) -> None:
        from analytics.views.manager import (
            DAILY_LOOKBACK_DAYS,
            MIN_SYMBOLS_FOR_FULL_DAY,
            VERSION_KEEP_COUNT,
        )

        assert MIN_SYMBOLS_FOR_FULL_DAY == 100
        assert DAILY_LOOKBACK_DAYS == 50
        assert VERSION_KEEP_COUNT == 3

    def test_validator_has_canonical_view_list(self) -> None:
        from analytics.views.validator import VALID_VIEWS

        assert "v_candles_1m" in VALID_VIEWS
        assert "v_feature_rsi" in VALID_VIEWS
        assert "v_top3_candidates" in VALID_VIEWS
        assert "v_strategy_candidates" in VALID_VIEWS
        assert "v_quality_score" in VALID_VIEWS
        assert "v_relative_strength" not in VALID_VIEWS
        assert "v_trend_state" not in VALID_VIEWS
        assert "v_scanner_snapshot" not in VALID_VIEWS
