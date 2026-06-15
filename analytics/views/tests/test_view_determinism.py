"""Determinism tests for DuckDB scanner/strategy views."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from analytics.views.scanner import ScannerViews
from analytics.views.strategy import StrategyViews


@pytest.fixture
def conn(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    """Create a temporary DuckDB connection with tied intraday scores."""
    db_path = tmp_path / "test_view_determinism.duckdb"
    c = duckdb.connect(str(db_path))

    c.execute("""
        CREATE TABLE m_intraday_snapshot AS
        SELECT * FROM (VALUES
            ('RELIANCE', 100.0, 100.0, 105.0, 99.0, 103.0, 1000, 1, 105.0, 99.0, 100.0, 103.0, 1000.0, 'Bullish', 1.0, 0.0, 0.0, 0.0, 1.0, 1.0, 50.0, 'BUY'),
            ('INFY', 200.0, 200.0, 205.0, 199.0, 203.0, 800, 1, 205.0, 199.0, 200.0, 203.0, 800.0, 'Bullish', 1.0, 0.0, 0.0, 0.0, 1.0, 1.0, 50.0, 'BUY'),
            ('TCS', 300.0, 300.0, 305.0, 299.0, 303.0, 900, 1, 305.0, 299.0, 300.0, 303.0, 900.0, 'Bullish', 1.0, 0.0, 0.0, 0.0, 1.0, 1.0, 50.0, 'BUY')
        ) AS t(
            symbol, ltp, day_open, day_high, day_low, day_close, day_volume, bars_today,
            sma_20, sma_50, roc_5, roc_10, roc_20, trend, relative_volume, close_5d,
            close_10d, close_20d, atr_approx, rsi_approx, intraday_score, signal
        )
    """)

    yield c
    c.close()


class TestScannerViewDeterminism:
    def test_top3_candidates_deterministic(self, conn: duckdb.DuckDBPyConnection) -> None:
        views = ScannerViews()
        views._create_top3_candidates(conn)

        symbols = []
        for _ in range(20):
            rows = conn.execute("SELECT symbol FROM v_top3_candidates").fetchall()
            symbols.append([r[0] for r in rows])

        assert all(s == symbols[0] for s in symbols)
        assert symbols[0] == sorted(symbols[0])

    def test_top10_candidates_deterministic(self, conn: duckdb.DuckDBPyConnection) -> None:
        views = ScannerViews()
        views._create_top10_candidates(conn)

        symbols = []
        for _ in range(20):
            rows = conn.execute("SELECT symbol FROM v_top10_candidates").fetchall()
            symbols.append([r[0] for r in rows])

        assert all(s == symbols[0] for s in symbols)
        assert symbols[0] == sorted(symbols[0])


class TestStrategyViewDeterminism:
    def test_strategy_candidates_deterministic(self, conn: duckdb.DuckDBPyConnection) -> None:
        views = StrategyViews()
        views._create_strategy_candidates(conn)

        symbols = []
        for _ in range(20):
            rows = conn.execute("SELECT symbol FROM v_strategy_candidates").fetchall()
            symbols.append([r[0] for r in rows])

        assert all(s == symbols[0] for s in symbols)
        assert symbols[0] == sorted(symbols[0])
