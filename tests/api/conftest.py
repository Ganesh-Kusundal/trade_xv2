"""Test fixtures for API contract tests.

Provides an in-memory mock DataCatalog so that symbol endpoints return
404 (not found) instead of crashing with 500 when no database is available.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.config import APIConfig
from api.deps import reset_container
from domain import Balance, Quote


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
    
    # Register mock services so endpoints return gracefully
    # instead of crashing with 'NoneType has no attribute'
    mock_catalog = MockDataCatalog()

    class _StubGateway:
        """Minimal stub so readiness check sees a non-None gateway."""

    class _StubViewManager:
        """Minimal stub so readiness check sees a non-None view_manager."""

    class _StubEventBus:
        """Minimal stub so readiness check sees a non-None event_bus."""

    return create_app(
        config=config,
        data_catalog=mock_catalog,
        datalake_gateway=_StubGateway(),
        view_manager=_StubViewManager(),
        event_bus=_StubEventBus(),
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


class StubLiveGateway:
    """Minimal gateway stub for /api/v1/live/* contract tests."""

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        return Quote(
            symbol="RELIANCE",
            ltp=Decimal("100.00"),
            open=Decimal("99.00"),
            high=Decimal("101.00"),
            low=Decimal("98.00"),
            close=Decimal("100.00"),
            volume=1000,
        )

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        return Decimal("100.00")

    def depth(self, symbol: str, exchange: str = "NSE"):
        from domain import DepthLevel, MarketDepth

        return MarketDepth(
            symbol=symbol,
            bids=[DepthLevel(price=Decimal("99.5"), quantity=10, orders=1)],
            asks=[DepthLevel(price=Decimal("100.5"), quantity=10, orders=1)],
        )

    def history(self, symbol, timeframe, start, end):
        import pandas as pd

        return pd.DataFrame([{"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10}])

    def positions(self):
        return []

    def holdings(self):
        return []

    def funds(self) -> Balance:
        return Balance(
            available_balance=Decimal("50000"),
            used_margin=Decimal("0"),
            total_balance=Decimal("50000"),
        )

    def get_orderbook(self):
        return []

    def get_trade_book(self):
        return []

    def option_chain(self, underlying: str, exchange: str = "NFO", expiry=None):
        from domain.derivatives import OptionChain

        return OptionChain(underlying=underlying, exchange=exchange)

    def future_chain(self, underlying: str, exchange: str = "NFO"):
        from domain import FutureChain

        return FutureChain(underlying=underlying, exchange=exchange)

    def describe(self):
        return {"broker": "stub", "connected": True}

    def capabilities(self):
        from brokers.common.gateway import BrokerCapabilities

        return BrokerCapabilities(websocket=True)

    @property
    def extended(self):
        ext = MagicMock()
        ext.get_user_profile.return_value = {"name": "stub"}
        ext.get_ledger.return_value = []
        ext.get_ip.return_value = {"ip": "127.0.0.1"}
        return ext


@pytest.fixture
def stub_live_gateway() -> StubLiveGateway:
    return StubLiveGateway()


@pytest.fixture
def live_client(stub_live_gateway: StubLiveGateway):
    reset_container()
    broker_service = SimpleNamespace(
        active_broker=stub_live_gateway,
        active_broker_name="dhan",
    )
    app = create_app(config=APIConfig(auth_mode="none"), broker_service=broker_service)
    client = TestClient(app)
    yield client
    reset_container()
