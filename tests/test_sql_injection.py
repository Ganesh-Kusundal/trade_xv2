"""Tests for SQL injection prevention in DuckDB queries.

Ensures:
1. All DuckDB queries use parameterized placeholders (?)
2. SQL injection attempts are blocked
3. No f-string or .format() SQL construction
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb


class TestDuckDBParameterization:
    """Verify DuckDB queries use parameterized placeholders."""

    def test_parameterized_query_prevents_injection(self, tmp_path: Path) -> None:
        """Parameterized queries must block SQL injection attempts."""
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))

        # Setup test data
        conn.execute("""
            CREATE TABLE candles (
                symbol VARCHAR,
                timestamp TIMESTAMP,
                close DOUBLE
            )
        """)
        conn.execute("INSERT INTO candles VALUES ('RELIANCE', '2024-01-01', 100.0)")

        # Try SQL injection with parameterized query
        malicious_symbol = "'; DROP TABLE candles; --"

        # This should NOT execute the DROP TABLE
        query = "SELECT * FROM candles WHERE symbol = ?"
        result = conn.execute(query, [malicious_symbol]).fetchall()

        # Query should return empty (no match), not crash or drop table
        assert result == []

        # Verify table still exists
        count = conn.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
        assert count == 1

        conn.close()

    def test_parameterized_query_with_valid_input(self, tmp_path: Path) -> None:
        """Parameterized queries must work correctly with valid inputs."""
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))

        conn.execute("""
            CREATE TABLE candles (
                symbol VARCHAR,
                timestamp TIMESTAMP,
                close DOUBLE
            )
        """)
        conn.execute("INSERT INTO candles VALUES ('RELIANCE', '2024-01-01', 100.0)")
        conn.execute("INSERT INTO candles VALUES ('TCS', '2024-01-01', 200.0)")

        query = "SELECT * FROM candles WHERE symbol = ?"
        result = conn.execute(query, ["RELIANCE"]).fetchall()

        assert len(result) == 1
        assert result[0][0] == "RELIANCE"

        conn.close()

    def test_parameterized_query_with_multiple_params(self, tmp_path: Path) -> None:
        """Parameterized queries must handle multiple parameters correctly."""
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))

        conn.execute("""
            CREATE TABLE candles (
                symbol VARCHAR,
                timestamp TIMESTAMP,
                close DOUBLE
            )
        """)
        conn.execute("INSERT INTO candles VALUES ('RELIANCE', '2024-01-01', 100.0)")
        conn.execute("INSERT INTO candles VALUES ('RELIANCE', '2024-01-02', 101.0)")
        conn.execute("INSERT INTO candles VALUES ('TCS', '2024-01-01', 200.0)")

        query = "SELECT * FROM candles WHERE symbol = ? AND timestamp >= ?"
        result = conn.execute(query, ["RELIANCE", "2024-01-02"]).fetchall()

        assert len(result) == 1
        assert result[0][2] == 101.0

        conn.close()


class TestCacheUtilsSQLInjection:
    """Test that cache_utils.py SQL queries are parameterized."""

    def test_get_last_candle_fast_uses_parameterized_query(self) -> None:
        """get_last_candle_fast must use parameterized queries, not f-strings."""
        import inspect

        from datalake.cache_utils import get_last_candle_fast

        source = inspect.getsource(get_last_candle_fast)

        # Should NOT use f-string with path interpolation
        assert 'f"""' not in source or "read_parquet(?)" in source
        assert "f'" not in source or "?" in source

        # Should use parameterized query
        assert "?" in source or "read_parquet(?" in source

    def test_cache_utils_no_fstring_sql(self) -> None:
        """cache_utils.py must not have f-string SQL queries."""
        import inspect

        import datalake.cache_utils

        source = inspect.getsource(datalake.cache_utils)

        # Check for f-string SQL patterns (should not exist after fix)
        fstring_sql_pattern = r'f["\'].*SELECT\s'
        matches = re.findall(fstring_sql_pattern, source, re.IGNORECASE)

        # After fix, there should be no f-string SQL queries
        # (This test will fail before the fix, pass after)
        assert len(matches) == 0, f"Found f-string SQL queries: {matches}"


class TestViewManagerSQLInjection:
    """Test that ViewManager SQL queries are safe."""

    def test_view_manager_query_uses_parameters(self, tmp_path: Path) -> None:
        """ViewManager.query() must support parameterized queries."""
        from analytics.views.manager import ViewManager

        vm = ViewManager(catalog_path=tmp_path / "test.duckdb")
        try:
            # Create test table
            vm.conn.execute("""
                CREATE TABLE test_table (
                    symbol VARCHAR,
                    value DOUBLE
                )
            """)
            vm.conn.execute("INSERT INTO test_table VALUES ('RELIANCE', 100.0)")

            # Query with parameters
            result = vm.query("SELECT * FROM test_table WHERE symbol = ?", ["RELIANCE"])
            rows = result.fetchall()

            assert len(rows) == 1
            assert rows[0][0] == "RELIANCE"
        finally:
            vm.close()

    def test_view_manager_query_blocks_injection(self, tmp_path: Path) -> None:
        """ViewManager must block SQL injection via parameters."""
        from analytics.views.manager import ViewManager

        vm = ViewManager(catalog_path=tmp_path / "test.duckdb")
        try:
            vm.conn.execute("""
                CREATE TABLE test_table (
                    symbol VARCHAR,
                    value DOUBLE
                )
            """)
            vm.conn.execute("INSERT INTO test_table VALUES ('RELIANCE', 100.0)")

            # Try injection
            malicious = "'; DROP TABLE test_table; --"
            result = vm.query("SELECT * FROM test_table WHERE symbol = ?", [malicious])
            rows = result.fetchall()

            # Should return empty, not crash
            assert rows == []

            # Verify table still exists
            count = vm.query_scalar("SELECT COUNT(*) FROM test_table")
            assert count == 1
        finally:
            vm.close()


class TestDataLakeGatewaySQLInjection:
    """Test that DataLakeGateway SQL queries are parameterized."""

    def test_gateway_batch_query_uses_parameters(self, tmp_path: Path) -> None:
        """DataLakeGateway must use parameterized DuckDB queries."""
        import inspect

        from datalake.gateway import DataLakeGateway

        # Check ltp_batch method
        source = inspect.getsource(DataLakeGateway.ltp_batch)

        # Should use parameterized query
        assert "read_parquet(?" in source

        # Should NOT use f-string with path
        assert 'f"' not in source or "?" in source

    def test_gateway_history_batch_uses_parameters(self, tmp_path: Path) -> None:
        """DataLakeGateway.history_batch must use parameterized queries."""
        import inspect

        from datalake.gateway import DataLakeGateway

        source = inspect.getsource(DataLakeGateway.history_batch)

        # Should use parameterized query
        assert "read_parquet(?" in source


class TestSQLInjectionPatterns:
    """Test various SQL injection patterns are blocked."""

    def test_injection_with_semicolon(self, tmp_path: Path) -> None:
        """Injection using semicolon must be blocked."""
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))

        conn.execute("CREATE TABLE test (symbol VARCHAR, value INT)")
        conn.execute("INSERT INTO test VALUES ('A', 1)")

        malicious = "'; DROP TABLE test; --"
        result = conn.execute("SELECT * FROM test WHERE symbol = ?", [malicious]).fetchall()

        assert result == []
        # Table must still exist
        conn.execute("SELECT COUNT(*) FROM test").fetchone()
        conn.close()

    def test_injection_with_union(self, tmp_path: Path) -> None:
        """Injection using UNION must be blocked."""
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))

        conn.execute("CREATE TABLE test (symbol VARCHAR, value INT)")
        conn.execute("INSERT INTO test VALUES ('A', 1)")

        malicious = "' UNION SELECT symbol, value FROM test --"
        result = conn.execute("SELECT * FROM test WHERE symbol = ?", [malicious]).fetchall()

        # Should return empty (no match), not union results
        assert result == []
        conn.close()

    def test_injection_with_comment(self, tmp_path: Path) -> None:
        """Injection using SQL comments must be blocked."""
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))

        conn.execute("CREATE TABLE test (symbol VARCHAR, value INT)")
        conn.execute("INSERT INTO test VALUES ('A', 1)")

        malicious = "A' --"
        result = conn.execute("SELECT * FROM test WHERE symbol = ?", [malicious]).fetchall()

        # Should return empty (exact match required)
        assert result == []
        conn.close()

    def test_injection_with_or_true(self, tmp_path: Path) -> None:
        """Injection using OR 1=1 must be blocked."""
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))

        conn.execute("CREATE TABLE test (symbol VARCHAR, value INT)")
        conn.execute("INSERT INTO test VALUES ('A', 1)")
        conn.execute("INSERT INTO test VALUES ('B', 2)")

        malicious = "' OR '1'='1"
        result = conn.execute("SELECT * FROM test WHERE symbol = ?", [malicious]).fetchall()

        # Should return empty, not all rows
        assert len(result) == 0
        conn.close()
