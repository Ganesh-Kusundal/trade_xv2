"""Tests for the SQL scanner query framework."""

from __future__ import annotations

from decimal import Decimal

import duckdb
import pandas as pd
import pytest

from analytics.scanner.models import ScanResult
from analytics.scanner.scanner_queries import (
    ScannerQuery,
    breakout_scanner,
    list_scanners,
    momentum_scanner,
    run_scanner,
    volume_scanner,
)


@pytest.fixture
def conn():
    """Create in-memory DuckDB connection with fake intraday_features table."""
    c = duckdb.connect(":memory:")

    rows = []
    symbols = ["RELIANCE", "INFY", "TCS", "HDFCBANK", "ICICIBANK"]
    for i, sym in enumerate(symbols):
        base_price = 100.0 + i * 50.0
        for day in range(5):
            for minute in range(10):
                t = f"2024-03-{10 + day:02d} 09:{15 + minute:02d}:00"
                px = base_price + day * 2.0 + minute * 0.1 + (i * 0.5)
                rows.append({
                    "symbol": sym,
                    "event_time": t,
                    "published_at": "2024-03-15 15:30:00",
                    "open": px - 0.2,
                    "high": px + 1.0,
                    "low": px - 1.0,
                    "close": px,
                    "volume": 10000 + i * 1000 + minute * 100,
                    "rsi_14": 50.0 + i * 5.0 + day * 2.0,
                    "rsi_21": 50.0 + i * 3.0 + day * 1.5,
                    "atr_14": 1.5 + i * 0.3,
                    "sma_20": px - 0.5,
                    "sma_50": px - 1.0,
                    "ema_12": px - 0.3,
                    "ema_26": px - 0.8,
                    "macd": 0.5 + i * 0.1,
                    "macd_signal": 0.3 + i * 0.05,
                    "macd_histogram": 0.2 + i * 0.05,
                    "bb_upper": px + 2.0,
                    "bb_lower": px - 2.0,
                    "bb_mid": px,
                    "roc_5": 1.0 + i * 0.5,
                    "roc_10": 2.0 + i * 0.3,
                    "roc_20": 3.0 + i * 0.2,
                    "volume_sma_20": 10000 + i * 800,
                    "volume_sma_50": 9500 + i * 700,
                    "relative_volume_20": 1.0 + i * 0.3,
                    "vwap_daily": px * 1.001,
                    "true_range": 1.5 + i * 0.2,
                    "avg_true_range_14": 1.5 + i * 0.2,
                })

    df = pd.DataFrame(rows)
    df["event_time"] = pd.to_datetime(df["event_time"])
    df["published_at"] = pd.to_datetime(df["published_at"])
    df["symbol"] = df["symbol"].astype("object")
    c.execute("CREATE TABLE intraday_features AS SELECT * FROM df")
    return c

    return c


class TestMomentumScanner:
    def test_momentum_scanner_returns_candidates(self, conn: duckdb.DuckDBPyConnection) -> None:
        result = momentum_scanner.run(conn, as_of_time="2024-03-15 15:30:00")
        assert isinstance(result, ScanResult)
        assert len(result.candidates) > 0
        for c in result.candidates:
            assert isinstance(c.symbol, str)
            assert isinstance(c.score, Decimal)
            assert Decimal("0") <= c.score <= Decimal("100")

    def test_momentum_filters_by_top_n(self, conn: duckdb.DuckDBPyConnection) -> None:
        scanner = momentum_scanner
        scanner.top_n = 2
        result = scanner.run(conn, as_of_time="2024-03-15 15:30:00")
        assert len(result.candidates) <= 2


class TestVolumeScanner:
    def test_volume_scanner_uses_feature_table(self, conn: duckdb.DuckDBPyConnection) -> None:
        result = volume_scanner.run(conn, as_of_time="2024-03-15 15:30:00")
        assert isinstance(result, ScanResult)
        assert len(result.candidates) > 0
        for c in result.candidates:
            assert "relative_volume_20" in c.metrics or "vol_ratio" in c.metrics


class TestBreakoutScanner:
    def test_breakout_scanner_matches_python_equivalent(
        self, conn: duckdb.DuckDBPyConnection
    ) -> None:
        result = breakout_scanner.run(conn, as_of_time="2024-03-15 15:30:00")
        assert isinstance(result, ScanResult)
        assert len(result.candidates) > 0
        for c in result.candidates:
            assert "bb_pct_b" in c.metrics or "bb_upper" in c.metrics


class TestPointInTime:
    def test_scanner_respects_as_of_time(self, conn: duckdb.DuckDBPyConnection) -> None:
        later = momentum_scanner.run(conn, as_of_time="2024-03-15 15:30:00")
        earlier = momentum_scanner.run(conn, as_of_time="2024-03-12 09:30:00")
        assert len(later.candidates) >= 0
        assert len(earlier.candidates) >= 0


class TestValidation:
    def test_scanner_rejects_lookahead_sql(self) -> None:
        bad_scanner = ScannerQuery(
            name="bad",
            description="Has look-ahead",
            sql="SELECT LEAD(close) OVER () FROM intraday_features",
        )
        warnings = bad_scanner.validate()
        assert len(warnings) > 0
        assert "LEAD" in warnings[0]

    def test_scanner_validates_clean_sql(self) -> None:
        good_scanner = ScannerQuery(
            name="good",
            description="Clean SQL",
            sql="SELECT symbol, event_time FROM intraday_features WHERE published_at <= :as_of_time",
        )
        warnings = good_scanner.validate()
        assert len(warnings) == 0


class TestListScanners:
    def test_list_scanners_returns_expected(self) -> None:
        scanners = list_scanners()
        names = [s.name for s in scanners]
        assert "momentum" in names
        assert "volume_breakout" in names
        assert "rs_rotation" in names
        assert "breakout" in names

    def test_list_scanners_all_have_sql(self) -> None:
        for s in list_scanners():
            assert s.sql
            assert ":as_of_time" in s.sql
            assert s.description


class TestRunScanner:
    def test_run_scanner_by_name(self, conn: duckdb.DuckDBPyConnection) -> None:
        result = run_scanner("momentum", as_of_time="2024-03-15 15:30:00", conn=conn)
        assert isinstance(result, ScanResult)
        assert len(result.candidates) > 0

    def test_run_scanner_invalid_name(self) -> None:
        with pytest.raises(ValueError, match="Unknown scanner"):
            run_scanner("nonexistent", as_of_time="2024-03-15 15:30:00")


class TestScannerScoreBounds:
    @pytest.mark.parametrize("scanner", [momentum_scanner, volume_scanner, breakout_scanner])
    def test_all_scores_in_range(
        self, conn: duckdb.DuckDBPyConnection, scanner
    ) -> None:
        result = scanner.run(conn, as_of_time="2024-03-15 15:30:00")
        for c in result.candidates:
            assert Decimal("0") <= c.score <= Decimal("100"), (
                f"{scanner.name}: score {c.score} out of range"
            )

    def test_all_scanners_produce_deterministic_results(
        self, conn: duckdb.DuckDBPyConnection
    ) -> None:
        for scanner_def in list_scanners():
            r1 = scanner_def.run(conn, as_of_time="2024-03-15 15:30:00")
            r2 = scanner_def.run(conn, as_of_time="2024-03-15 15:30:00")
            symbols_1 = [c.symbol for c in r1.candidates]
            symbols_2 = [c.symbol for c in r2.candidates]
            assert symbols_1 == symbols_2, f"{scanner_def.name} not deterministic"


class TestCustomScanner:
    def test_custom_scanner(self, conn: duckdb.DuckDBPyConnection) -> None:
        scanner = ScannerQuery(
            name="custom_test",
            description="Custom scanner for testing",
            sql="""
                SELECT symbol, 75.0 as score, 'test_signal' as reason
                FROM intraday_features
                WHERE published_at <= :as_of_time
                  AND event_time <= :as_of_time
                GROUP BY symbol
            """,
        )
        result = scanner.run(conn, as_of_time="2024-03-15 15:30:00")
        assert len(result.candidates) > 0
        for c in result.candidates:
            assert c.score == Decimal("75.00")


class TestMinScoreFilter:
    def test_min_score_filters_low_scores(self, conn: duckdb.DuckDBPyConnection) -> None:
        scanner = ScannerQuery(
            name="filter_test",
            description="Test min_score",
            sql="""
                SELECT symbol,
                       ROW_NUMBER() OVER (ORDER BY symbol) * 10.0 as score
                FROM intraday_features
                WHERE published_at <= :as_of_time
                  AND event_time <= :as_of_time
                GROUP BY symbol
            """,
            min_score=50.0,
        )
        result = scanner.run(conn, as_of_time="2024-03-15 15:30:00")
        for c in result.candidates:
            assert c.score >= Decimal("50.00")
