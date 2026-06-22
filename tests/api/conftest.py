"""Test fixtures for API contract tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi.testclient import TestClient

from datalake.api.main import create_app
from datalake.api.config import APIConfig


@pytest.fixture
def app():
    """Create FastAPI test application."""
    config = APIConfig(
        host="127.0.0.1",
        port=8000,
        cors_origins=["http://localhost:3000"],
        max_page_size=1000,
        default_page_size=100,
    )
    
    return create_app(config=config)


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
