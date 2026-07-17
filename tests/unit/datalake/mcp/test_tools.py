"""Integration tests for the datalake MCP tool implementations.

Real components throughout: a real Parquet fixture written via
HistoricalDataLoader (same pattern as test_loader_merge.py), a real
DataCatalog, and DatalakeTools reading from real disk -- no mocks, per
context/code-standards.md's "integration tests only" convention.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from datalake.core.duckdb_utils import get_pool
from datalake.ingestion.loader import HistoricalDataLoader
from datalake.mcp import sql_guard
from datalake.mcp.server import create_server
from datalake.mcp.tools import DatalakeTools
from datalake.storage.catalog import DataCatalog


def _candles(dates: list[str], base_price: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(dates),
            "symbol": ["RELIANCE"] * len(dates),
            "exchange": ["NSE"] * len(dates),
            "open": [base_price] * len(dates),
            "high": [base_price + 1] * len(dates),
            "low": [base_price - 1] * len(dates),
            "close": [base_price + 0.5] * len(dates),
            "volume": [1000] * len(dates),
            "oi": [0] * len(dates),
        }
    )


class _FakeGateway:
    """Returns its configured DataFrame once, then empty -- mirrors
    test_loader_merge.py's FakeGateway (handles both the single-call
    lookback_days= signature and the chunked from_date=/to_date= calls
    loader.py's _fetch_history_chunked() makes)."""

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df
        self._served = False

    def history(
        self, symbol, *, exchange, timeframe, lookback_days=None, from_date=None, to_date=None
    ) -> pd.DataFrame:
        if self._served:
            return self._df.iloc[0:0]
        self._served = True
        return self._df


@pytest.fixture
def tools(tmp_path: Path) -> DatalakeTools:
    """A DatalakeTools instance over a tmp_path datalake with one real
    symbol (RELIANCE, 3 candles) written and catalog-registered."""
    catalog = DataCatalog(str(tmp_path))
    loader = HistoricalDataLoader(root=str(tmp_path), catalog=catalog)
    dates = ["2026-01-05 09:15:00", "2026-01-05 09:16:00", "2026-01-06 09:15:00"]
    loader.download_symbol(
        "RELIANCE", _FakeGateway(_candles(dates)), years=1, timeframe="1m", exchange="NSE"
    )
    catalog.close()
    # DataCatalog.close() only decrements DuckDBPool's ref-count; it never
    # actually closes the connection (see DuckDBPool.release() docstring --
    # closing on every release would be wasteful in a long-lived server).
    # DuckDB refuses a read-only connection while a read-write one is still
    # open on the same file, so force-close it before DatalakeTools opens
    # its own read-only DataCatalog on the same path.
    get_pool().close(str(tmp_path / "catalog.duckdb"))
    return DatalakeTools(root=str(tmp_path))


class TestHistoryAndListing:
    def test_history_returns_fixture_rows(self, tools: DatalakeTools) -> None:
        rows = tools.history("RELIANCE", timeframe="1m", years=1)
        assert len(rows) == 3
        assert rows[0]["symbol"] == "RELIANCE"
        assert rows[0]["close"] == pytest.approx(100.5)

    def test_latest_returns_tail(self, tools: DatalakeTools) -> None:
        rows = tools.latest("RELIANCE", timeframe="1m", n=1)
        assert len(rows) == 1
        assert rows[0]["timestamp"] == "2026-01-06 09:15:00"

    def test_list_symbols_includes_fixture(self, tools: DatalakeTools) -> None:
        assert "RELIANCE" in tools.list_symbols(timeframe="1m")


class TestCatalogMetadata:
    def test_symbol_status_reflects_registration(self, tools: DatalakeTools) -> None:
        status = tools.symbol_status("RELIANCE")
        assert status is not None
        assert status["total_rows"] == 3
        assert status["first_date"] == "2026-01-05"
        assert status["last_date"] == "2026-01-06"

    def test_symbol_status_none_for_unknown_symbol(self, tools: DatalakeTools) -> None:
        assert tools.symbol_status("DOES_NOT_EXIST") is None

    def test_catalog_summary_counts_fixture(self, tools: DatalakeTools) -> None:
        summary = tools.catalog_summary()
        assert summary["symbols"] == 1
        assert summary["total_rows"] == 3


class TestQualityAndHealth:
    def test_quality_check_reports_real_row_count(self, tools: DatalakeTools) -> None:
        report = tools.quality_check("RELIANCE", timeframe="1m")
        assert report["total_rows"] == 3
        assert report["symbol"] == "RELIANCE"
        assert "summary_text" in report

    def test_health_check_finds_no_issues_on_clean_fixture(self, tools: DatalakeTools) -> None:
        result = tools.health_check(timeframe="1m", min_rows=1)
        assert result["duplicate_timestamps"]["count"] == 0
        assert result["ohlc_inconsistent"]["count"] == 0
        assert result["negative_volume"]["count"] == 0
        assert result["future_timestamps"]["count"] == 0


class TestQuery:
    def test_query_returns_real_aggregate(self, tools: DatalakeTools) -> None:
        rows = tools.query("SELECT symbol, count(*) AS n FROM candles GROUP BY symbol")
        assert rows == [{"symbol": "RELIANCE", "n": 3}]

    def test_query_rejects_drop_table(self, tools: DatalakeTools) -> None:
        with pytest.raises(ValueError, match="SELECT/WITH"):
            tools.query("DROP TABLE candles")

    def test_query_rejects_chained_statements(self, tools: DatalakeTools) -> None:
        with pytest.raises(ValueError, match="single statement"):
            tools.query("SELECT * FROM candles; DELETE FROM candles")

    def test_query_rejects_filesystem_read_functions(self, tools: DatalakeTools) -> None:
        with pytest.raises(ValueError, match="disallowed"):
            tools.query("SELECT * FROM read_parquet('/etc/passwd')")


class TestSqlGuard:
    """Direct unit coverage of validate_select()'s edge cases."""

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT * FROM candles",
            "select * from candles;",
            "WITH x AS (SELECT * FROM candles) SELECT * FROM x",
        ],
    )
    def test_allows_plain_select(self, sql: str) -> None:
        sql_guard.validate_select(sql)  # must not raise

    def test_rejects_empty_query(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            sql_guard.validate_select("   ")

    @pytest.mark.parametrize(
        "sql",
        [
            "INSERT INTO candles VALUES (1)",
            "ATTACH 'evil.db' AS x",
            "PRAGMA database_list",
            "COPY candles TO 'out.csv'",
        ],
    )
    def test_rejects_ddl_dml(self, sql: str) -> None:
        with pytest.raises(ValueError):
            sql_guard.validate_select(sql)


class TestServerWiring:
    async def test_create_server_registers_all_tools(self) -> None:
        srv = create_server(root="data/lake")
        tool_list = await srv.list_tools()
        names = {t.name for t in tool_list}
        assert names == {
            "history",
            "latest",
            "list_symbols",
            "symbol_status",
            "catalog_summary",
            "quality_check",
            "health_check",
            "query",
            "float_data",
        }
