"""Test fixtures for API contract tests.

Provides an in-memory mock DataCatalog so that symbol endpoints return
404 (not found) instead of crashing with 500 when no database is available.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from datalake.api.main import create_app
from datalake.api.config import APIConfig


class MockDuckDBConnection:
    """DuckDB connection mock that returns empty results for any query."""
    
    def execute(self, query: str, params: list | None = None):
        return self
    
    def fetchone(self):
        return None
    
    def fetchall(self):
        return []
    
    def description(self):
        return []


class MockDataCatalog:
    """Mock DataCatalog that returns empty results gracefully."""
    
    def __init__(self):
        self._conn = MockDuckDBConnection()
    
    @property
    def conn(self):
        return self._conn
    
    def close(self):
        pass


@pytest.fixture
def app():
    """Create FastAPI test application with mocked services."""
    config = APIConfig(
        host="127.0.0.1",
        port=8000,
        cors_origins=["http://localhost:3000"],
        max_page_size=1000,
        default_page_size=100,
    )
    
    # Register mock services so symbol endpoints return 404 gracefully
    # instead of crashing with 'NoneType has no attribute conn'
    mock_catalog = MockDataCatalog()
    
    return create_app(
        config=config,
        data_catalog=mock_catalog,
    )


@pytest.fixture
def client(app):
    """Create synchronous test client."""
    return TestClient(app)


@pytest.fixture
def test_symbol():
    """Test symbol for API calls."""
    return "RELIANCE"


@pytest.fixture
def test_universe():
    """Test universe name."""
    return "nifty50"


@pytest.fixture
def test_timeframe():
    """Test timeframe."""
    return "1m"


@pytest.fixture
def test_date_range():
    """Test date range (last 7 days in milliseconds)."""
    import time
    now_ms = int(time.time() * 1000)
    seven_days_ms = 7 * 24 * 60 * 60 * 1000
    return {
        "from_ts": now_ms - seven_days_ms,
        "to_ts": now_ms,
    }
