"""Test DuckDB catalog schema creation and backward compatibility.

These tests verify that:
1. The full catalog schema can be created from a blank database
2. All expected tables exist after schema creation
3. Required columns exist in each table with correct types
4. Schema creation is idempotent (creating twice doesn't fail)
5. Data can be inserted and queried through the created schema
6. Migration version tracking works correctly
"""
from __future__ import annotations

from datetime import date

import duckdb
import pytest

from datalake.core.migrations import CURRENT_SCHEMA_VERSION, apply_migrations
from datalake.storage.catalog import DataCatalog


# All tables created by DataCatalog._init_schema + migrations
EXPECTED_TABLES = {
    "symbols",
    "data_quality",
    "download_jobs",
    "universe_history",
    "symbol_metadata_history",
    "data_versions",
    "schema_migrations",
    "universe_symbols",
}


def _get_tables(conn: duckdb.DuckDBPyConnection) -> set[str]:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    return {row[0] for row in rows}


def _get_columns(conn: duckdb.DuckDBPyConnection, table: str) -> dict[str, str]:
    rows = conn.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'main' AND table_name = ?",
        [table],
    ).fetchall()
    return {name: dtype for name, dtype in rows}


@pytest.fixture
def fresh_catalog(tmp_path):
    """Create a fresh DataCatalog backed by tmp_path."""
    catalog = DataCatalog(root=str(tmp_path))
    yield catalog
    catalog.close()


def _init_schema_on_conn(conn: duckdb.DuckDBPyConnection) -> None:
    """Apply the full catalog schema directly on a connection."""
    DataCatalog._create_symbols_table(conn)
    DataCatalog._create_data_quality_table(conn)
    DataCatalog._create_download_jobs_table(conn)
    DataCatalog._create_universe_history_table(conn)
    DataCatalog._create_symbol_metadata_history_table(conn)
    DataCatalog._create_data_versions_table(conn)
    apply_migrations(conn)


@pytest.fixture
def fresh_in_memory():
    """Create a fresh in-memory connection with schema applied."""
    conn = duckdb.connect(":memory:")
    _init_schema_on_conn(conn)
    yield conn
    conn.close()


class TestSchemaCreation:
    def test_creates_all_expected_tables(self, fresh_in_memory):
        tables = _get_tables(fresh_in_memory)
        missing = EXPECTED_TABLES - tables
        assert not missing, f"Missing tables after schema init: {missing}"

    def test_creates_via_catalog_constructor(self, fresh_catalog):
        tables = _get_tables(fresh_catalog.conn)
        missing = EXPECTED_TABLES - tables
        assert not missing, f"Missing tables after DataCatalog init: {missing}"

    def test_idempotent_creation(self, tmp_path):
        """Creating the schema twice via DataCatalog doesn't fail."""
        catalog1 = DataCatalog(root=str(tmp_path))
        tables1 = _get_tables(catalog1.conn)
        catalog1.close()

        catalog2 = DataCatalog(root=str(tmp_path))
        tables2 = _get_tables(catalog2.conn)
        catalog2.close()

        assert tables1 == tables2
        assert EXPECTED_TABLES <= tables2

    def test_idempotent_in_memory(self):
        """Calling schema init twice on the same connection doesn't fail."""
        conn = duckdb.connect(":memory:")
        try:
            _init_schema_on_conn(conn)
            _init_schema_on_conn(conn)  # second call is no-op (IF NOT EXISTS)
            tables = _get_tables(conn)
            assert EXPECTED_TABLES <= tables
        finally:
            conn.close()


class TestSchemaColumns:
    def test_symbols_columns(self, fresh_in_memory):
        cols = _get_columns(fresh_in_memory, "symbols")
        expected = {
            "symbol": "VARCHAR",
            "exchange": "VARCHAR",
            "instrument_type": "VARCHAR",
            "sector": "VARCHAR",
            "isin": "VARCHAR",
            "lot_size": "INTEGER",
            "tick_size": "DOUBLE",
            "first_date": "DATE",
            "last_date": "DATE",
            "total_rows": "BIGINT",
            "timeframe": "VARCHAR",
            "parquet_path": "VARCHAR",
            "created_at": "TIMESTAMP",
            "updated_at": "TIMESTAMP",
        }
        for col, dtype in expected.items():
            assert col in cols, f"Missing column {col} in symbols"
            assert cols[col] == dtype, f"symbols.{col}: expected {dtype}, got {cols[col]}"

    def test_data_quality_columns(self, fresh_in_memory):
        cols = _get_columns(fresh_in_memory, "data_quality")
        for col in ("symbol", "check_date", "timeframe", "total_rows",
                     "missing_candles", "duplicate_candles", "gap_days",
                     "completeness_pct", "status"):
            assert col in cols, f"Missing column {col} in data_quality"

    def test_download_jobs_columns(self, fresh_in_memory):
        cols = _get_columns(fresh_in_memory, "download_jobs")
        for col in ("job_id", "universe", "timeframe", "symbols_total",
                     "symbols_completed", "symbols_failed", "status",
                     "started_at", "completed_at"):
            assert col in cols, f"Missing column {col} in download_jobs"

    def test_universe_history_columns(self, fresh_in_memory):
        cols = _get_columns(fresh_in_memory, "universe_history")
        for col in ("universe", "symbol", "effective_date", "end_date", "added_at"):
            assert col in cols, f"Missing column {col} in universe_history"

    def test_symbol_metadata_history_columns(self, fresh_in_memory):
        cols = _get_columns(fresh_in_memory, "symbol_metadata_history")
        for col in ("symbol", "effective_date", "end_date", "lot_size",
                     "tick_size", "sector", "isin", "instrument_type", "added_at"):
            assert col in cols, f"Missing column {col} in symbol_metadata_history"

    def test_data_versions_columns(self, fresh_in_memory):
        cols = _get_columns(fresh_in_memory, "data_versions")
        for col in ("table_name", "version_id", "min_event_time", "max_event_time",
                     "min_published_at", "max_published_at", "row_count", "created_at"):
            assert col in cols, f"Missing column {col} in data_versions"

    def test_universe_symbols_columns(self, fresh_in_memory):
        cols = _get_columns(fresh_in_memory, "universe_symbols")
        assert "universe" in cols
        assert "symbol" in cols


class TestMigrationVersioning:
    def test_initial_version_is_current(self, fresh_in_memory):
        version = apply_migrations(fresh_in_memory)
        assert version == CURRENT_SCHEMA_VERSION

    def test_version_tracking_table_created(self, fresh_in_memory):
        apply_migrations(fresh_in_memory)
        rows = fresh_in_memory.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        versions = [r[0] for r in rows]
        assert CURRENT_SCHEMA_VERSION in versions

    def test_repeated_migration_is_noop(self, fresh_in_memory):
        apply_migrations(fresh_in_memory)
        # Second call should not insert a new row for the same version
        count_before = fresh_in_memory.execute(
            "SELECT COUNT(*) FROM schema_migrations"
        ).fetchone()[0]
        apply_migrations(fresh_in_memory)
        count_after = fresh_in_memory.execute(
            "SELECT COUNT(*) FROM schema_migrations"
        ).fetchone()[0]
        assert count_after == count_before


class TestSchemaDataOperations:
    def test_register_and_query_symbol(self, fresh_catalog):
        from datalake.core.duckdb_utils import get_pool

        fresh_catalog.register_symbol(
            "RELIANCE",
            exchange="NSE",
            first_date=date(2020, 1, 1),
            last_date=date(2026, 6, 10),
            total_rows=463000,
        )
        # get_symbol opens a read-only connection; close writer first
        fresh_catalog.close()
        get_pool().close(fresh_catalog._db_path)

        reader = DataCatalog(root=str(fresh_catalog._root), read_only=True)
        result = reader.get_symbol("RELIANCE")
        reader.close()
        assert result is not None
        assert result["symbol"] == "RELIANCE"
        assert result["total_rows"] == 463000

    def test_record_quality(self, fresh_catalog):
        fresh_catalog.record_quality(
            "TCS",
            total_rows=100000,
            missing_candles=3,
            completeness_pct=99.7,
            status="OK",
        )
        row = fresh_catalog.conn.execute(
            "SELECT total_rows, status FROM data_quality WHERE symbol = 'TCS'"
        ).fetchone()
        assert row is not None
        assert row[0] == 100000
        assert row[1] == "OK"

    def test_register_universe_snapshot(self, fresh_catalog):
        symbols = ["RELIANCE", "TCS", "HDFCBANK"]
        count = fresh_catalog.register_universe_snapshot("NIFTY50", symbols)
        assert count == 3
        result = fresh_catalog.get_universe_as_of("NIFTY50", date.today())
        assert set(result) == set(symbols)

    def test_register_symbol_metadata(self, fresh_catalog):
        fresh_catalog.register_symbol_metadata_snapshot(
            "RELIANCE",
            lot_size=1,
            tick_size=0.05,
            sector="Oil & Gas",
            isin="INE002A01018",
        )
        row = fresh_catalog.conn.execute(
            "SELECT lot_size, sector, isin FROM symbol_metadata_history "
            "WHERE symbol = 'RELIANCE'"
        ).fetchone()
        assert row is not None
        assert row[0] == 1
        assert row[1] == "Oil & Gas"
        assert row[2] == "INE002A01018"

    def test_universe_symbols_via_migration(self, fresh_in_memory):
        fresh_in_memory.execute(
            "INSERT INTO universe_symbols (universe, symbol) VALUES ('NIFTY50', 'RELIANCE')"
        )
        row = fresh_in_memory.execute(
            "SELECT symbol FROM universe_symbols WHERE universe = 'NIFTY50'"
        ).fetchone()
        assert row[0] == "RELIANCE"
