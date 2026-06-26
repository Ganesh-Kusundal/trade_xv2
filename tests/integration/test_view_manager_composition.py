"""Integration tests for ViewManager composition.

Verifies that ViewManager correctly composes the 3 extracted modules from Phase 6:
- ViewRegistry (view introspection)
- QueryExecutor (SQL execution)
- CacheManager (materialization)

These tests use REAL DuckDB connections, not mocks.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import duckdb
import pytest

from analytics.views.manager import ViewManager


@pytest.fixture
def temp_catalog() -> Path:
    """Create a temporary DuckDB catalog path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        catalog_path = Path(tmpdir) / "test_analytics.duckdb"
        yield catalog_path


class TestViewManagerComposition:
    """Verify ViewManager correctly composes extracted modules."""

    def test_view_manager_composes_all_modules(self, temp_catalog: Path) -> None:
        """Verify __init__ creates _registry, _executor, _cache."""
        vm = ViewManager(catalog_path=temp_catalog)

        # Verify all 3 modules are instantiated
        assert hasattr(vm, "_registry"), "ViewManager must have _registry attribute"
        assert hasattr(vm, "_executor"), "ViewManager must have _executor attribute"
        assert hasattr(vm, "_cache"), "ViewManager must have _cache attribute"

        # Verify they are the correct types
        from analytics.views.view_registry import ViewRegistry
        from analytics.views.query_executor import QueryExecutor
        from analytics.views.cache_manager import CacheManager

        assert isinstance(vm._registry, ViewRegistry), (
            f"_registry should be ViewRegistry, got {type(vm._registry)}"
        )
        assert isinstance(vm._executor, QueryExecutor), (
            f"_executor should be QueryExecutor, got {type(vm._executor)}"
        )
        assert isinstance(vm._cache, CacheManager), (
            f"_cache should be CacheManager, got {type(vm._cache)}"
        )

        vm.close()

    def test_list_views_delegates_to_registry(self, temp_catalog: Path) -> None:
        """Verify list_views() returns views from ViewRegistry."""
        vm = ViewManager(catalog_path=temp_catalog)

        # Create a view directly on the connection
        vm.conn.execute("CREATE VIEW test_view AS SELECT 1 as value")

        # Verify delegation: list_views should return the view we just created
        views = vm.list_views()
        assert isinstance(views, list), "list_views() must return a list"
        assert len(views) > 0, "list_views() should return at least 1 view"

        # Verify the view is in the list
        view_names = [v["name"] for v in views]
        assert "test_view" in view_names, (
            f"test_view should be in views, got: {view_names}"
        )

        # Verify view structure matches ViewRegistry format
        assert "name" in views[0], "View dict must have 'name' key"
        assert "definition" in views[0], "View dict must have 'definition' key"

        vm.close()

    def test_query_delegates_to_executor(self, temp_catalog: Path) -> None:
        """Verify query() executes SQL via QueryExecutor."""
        vm = ViewManager(catalog_path=temp_catalog)

        # Create a table to query
        vm.conn.execute("CREATE TABLE test_table AS SELECT 42 as answer")

        # Execute a query through ViewManager (which delegates to QueryExecutor)
        result = vm.query("SELECT answer FROM test_table")

        # Verify the query executed and returned results
        assert result is not None, "query() must return a result"
        rows = result.fetchall()
        assert len(rows) == 1, "Should return 1 row"
        assert rows[0][0] == 42, f"Expected answer=42, got {rows[0][0]}"

        vm.close()

    def test_materialize_delegates_to_cache_manager(self, temp_catalog: Path) -> None:
        """Verify materialize() uses CacheManager with connection."""
        vm = ViewManager(catalog_path=temp_catalog)

        # Create a source table
        vm.conn.execute(
            "CREATE TABLE source_data AS SELECT 'test' as symbol, 100 as price"
        )

        # Materialize a table (delegates to CacheManager)
        elapsed = vm.materialize(
            "test_materialized",
            "SELECT symbol, price FROM source_data",
        )

        # Register the materialized table (makes it queryable)
        vm.register_materialized("test_materialized")

        # Verify materialization completed
        assert isinstance(elapsed, float), "materialize() must return elapsed time as float"
        assert elapsed >= 0, "Elapsed time must be non-negative"

        # Verify the materialized table can be queried
        result = vm.query("SELECT symbol, price FROM test_materialized")
        rows = result.fetchall()
        assert len(rows) == 1, "Materialized table should have 1 row"
        assert rows[0][0] == "test", f"Expected symbol='test', got {rows[0][0]}"
        assert rows[0][1] == 100, f"Expected price=100, got {rows[0][1]}"

        vm.close()

    def test_close_releases_all_resources(self, temp_catalog: Path) -> None:
        """Verify close() releases connections from all modules."""
        vm = ViewManager(catalog_path=temp_catalog)

        # Force connection creation
        _ = vm.conn
        _ = vm.list_views()

        # Close the ViewManager
        vm.close()

        # Verify ViewManager's connection is released
        assert vm._conn is None, "ViewManager._conn should be None after close()"

        # Verify ViewRegistry's connection is released
        assert vm._registry._conn is None, (
            "ViewRegistry._conn should be None after close()"
        )

        # Note: QueryExecutor and CacheManager don't hold their own connections;
        # they receive connection providers from ViewManager, so no need to check them.

    def test_view_count_accurate_after_composition(self, temp_catalog: Path) -> None:
        """Verify view_count() matches registry."""
        vm = ViewManager(catalog_path=temp_catalog)

        # Initial count should be 0
        initial_count = vm.view_count()
        assert initial_count == 0, f"Initial view count should be 0, got {initial_count}"

        # Create 3 views
        vm.conn.execute("CREATE VIEW view_a AS SELECT 1")
        vm.conn.execute("CREATE VIEW view_b AS SELECT 2")
        vm.conn.execute("CREATE VIEW view_c AS SELECT 3")

        # Verify count increased
        new_count = vm.view_count()
        assert new_count == 3, f"View count should be 3 after creating 3 views, got {new_count}"

        # Verify view_count() delegates to ViewRegistry
        registry_count = vm._registry.view_count()
        assert new_count == registry_count, (
            f"ViewManager.view_count() ({new_count}) must match ViewRegistry.view_count() ({registry_count})"
        )

        vm.close()
