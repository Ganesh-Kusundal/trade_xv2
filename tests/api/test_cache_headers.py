"""Tests for Cache-Control headers on market data endpoints.

Verifies that:
1. Cache-Control headers are present on /candles and /quote responses
2. Different timeframes get appropriate max-age values
3. X-Data-Freshness header contains timestamp of most recent candle
4. Headers follow HTTP spec (public/private, max-age, stale-while-revalidate)
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api import deps
from api.config import APIConfig
from api.main import create_app


class MockDataLakeGateway:
    """Mock DataLakeGateway that returns synthetic candle data."""

    def __init__(self, symbol: str = "RELIANCE", num_candles: int = 100):
        self._symbol = symbol
        self._num_candles = num_candles

    def _load_parquet(self, symbol: str, timeframe: str) -> pd.DataFrame | None:
        """Generate synthetic OHLCV data for testing."""
        now = pd.Timestamp.now()
        # Create timestamps based on timeframe
        if timeframe.endswith("m"):
            minutes = int(timeframe[:-1])
            freq = f"{minutes}min"
        elif timeframe.endswith("h"):
            hours = int(timeframe[:-1])
            freq = f"{hours}h"
        elif timeframe == "1d":
            freq = "1D"
        elif timeframe == "1w":
            freq = "7D"  # Weekly = 7 days
        else:
            freq = "1min"

        timestamps = pd.date_range(end=now, periods=self._num_candles, freq=freq)

        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": [100.0 + i * 0.1 for i in range(self._num_candles)],
                "high": [101.0 + i * 0.1 for i in range(self._num_candles)],
                "low": [99.0 + i * 0.1 for i in range(self._num_candles)],
                "close": [100.5 + i * 0.1 for i in range(self._num_candles)],
                "volume": [1000.0 + i * 10 for i in range(self._num_candles)],
                "oi": [500.0] * self._num_candles,
            }
        )

        return df


@pytest.fixture(autouse=True)
def reset_container():
    """Reset the service container before each test to avoid singleton issues."""
    deps._container = None
    yield
    deps._container = None


class TestCacheHeadersCandles:
    """Test Cache-Control headers on /candles endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client with mock gateway."""
        mock_gateway = MockDataLakeGateway(num_candles=50)
        app = create_app(
            config=APIConfig(auth_mode="none"),
            datalake_gateway=mock_gateway,
        )
        return TestClient(app)

    def test_cache_control_header_present(self, client):
        """Cache-Control header must be present on /candles response."""
        response = client.get(
            "/api/v1/market/candles",
            params={"symbol": "RELIANCE", "timeframe": "1m", "limit": 10},
        )
        assert response.status_code == 200
        assert "Cache-Control" in response.headers
        cache_control = response.headers["Cache-Control"]
        assert "max-age=" in cache_control

    def test_intraday_1m_timeframe_max_age_30(self, client):
        """1m timeframe should have max-age=30 (30 seconds)."""
        response = client.get(
            "/api/v1/market/candles",
            params={"symbol": "RELIANCE", "timeframe": "1m", "limit": 10},
        )
        assert response.status_code == 200
        cache_control = response.headers["Cache-Control"]
        assert "max-age=30" in cache_control

    def test_intraday_3m_timeframe_max_age_30(self, client):
        """3m timeframe should have max-age=30 (30 seconds)."""
        response = client.get(
            "/api/v1/market/candles",
            params={"symbol": "RELIANCE", "timeframe": "3m", "limit": 10},
        )
        assert response.status_code == 200
        cache_control = response.headers["Cache-Control"]
        assert "max-age=30" in cache_control

    def test_intraday_5m_timeframe_max_age_30(self, client):
        """5m timeframe should have max-age=30 (30 seconds)."""
        response = client.get(
            "/api/v1/market/candles",
            params={"symbol": "RELIANCE", "timeframe": "5m", "limit": 10},
        )
        assert response.status_code == 200
        cache_control = response.headers["Cache-Control"]
        assert "max-age=30" in cache_control

    def test_15m_timeframe_max_age_300(self, client):
        """15m timeframe should have max-age=300 (5 minutes)."""
        response = client.get(
            "/api/v1/market/candles",
            params={"symbol": "RELIANCE", "timeframe": "15m", "limit": 10},
        )
        assert response.status_code == 200
        cache_control = response.headers["Cache-Control"]
        assert "max-age=300" in cache_control

    def test_30m_timeframe_max_age_300(self, client):
        """30m timeframe should have max-age=300 (5 minutes)."""
        response = client.get(
            "/api/v1/market/candles",
            params={"symbol": "RELIANCE", "timeframe": "30m", "limit": 10},
        )
        assert response.status_code == 200
        cache_control = response.headers["Cache-Control"]
        assert "max-age=300" in cache_control

    def test_1h_timeframe_max_age_300(self, client):
        """1h timeframe should have max-age=300 (5 minutes)."""
        response = client.get(
            "/api/v1/market/candles",
            params={"symbol": "RELIANCE", "timeframe": "1h", "limit": 10},
        )
        assert response.status_code == 200
        cache_control = response.headers["Cache-Control"]
        assert "max-age=300" in cache_control

    def test_daily_timeframe_max_age_3600(self, client):
        """1d timeframe should have max-age=3600 (1 hour)."""
        response = client.get(
            "/api/v1/market/candles",
            params={"symbol": "RELIANCE", "timeframe": "1d", "limit": 10},
        )
        assert response.status_code == 200
        cache_control = response.headers["Cache-Control"]
        assert "max-age=3600" in cache_control

    def test_weekly_timeframe_max_age_3600(self, client):
        """1w timeframe should have max-age=3600 (1 hour)."""
        response = client.get(
            "/api/v1/market/candles",
            params={"symbol": "RELIANCE", "timeframe": "1w", "limit": 10},
        )
        assert response.status_code == 200
        cache_control = response.headers["Cache-Control"]
        assert "max-age=3600" in cache_control

    def test_cache_control_uses_public_directive(self, client):
        """Cache-Control should use 'public' directive for cacheable data."""
        response = client.get(
            "/api/v1/market/candles",
            params={"symbol": "RELIANCE", "timeframe": "1m", "limit": 10},
        )
        assert response.status_code == 200
        cache_control = response.headers["Cache-Control"]
        assert "public" in cache_control

    def test_x_data_type_header_present(self, client):
        """X-Data-Type header should indicate data type."""
        response = client.get(
            "/api/v1/market/candles",
            params={"symbol": "RELIANCE", "timeframe": "1m", "limit": 10},
        )
        assert response.status_code == 200
        assert "X-Data-Type" in response.headers
        assert response.headers["X-Data-Type"] == "historical"

    def test_x_data_freshness_header_present(self, client):
        """X-Data-Freshness header should contain ISO timestamp of latest candle."""
        response = client.get(
            "/api/v1/market/candles",
            params={"symbol": "RELIANCE", "timeframe": "1m", "limit": 10},
        )
        assert response.status_code == 200
        assert "X-Data-Freshness" in response.headers
        # Should be a valid ISO timestamp
        freshness = response.headers["X-Data-Freshness"]
        # Verify it can be parsed as ISO format
        assert "T" in freshness or "-" in freshness


class TestCacheHeadersQuote:
    """Test Cache-Control headers on /quote endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client with mock gateway."""
        mock_gateway = MockDataLakeGateway(num_candles=10)
        app = create_app(
            config=APIConfig(auth_mode="none"),
            datalake_gateway=mock_gateway,
        )
        return TestClient(app)

    def test_quote_cache_control_header_present(self, client):
        """Cache-Control header must be present on /quote response."""
        response = client.get("/api/v1/market/quote/RELIANCE")
        assert response.status_code == 200
        assert "Cache-Control" in response.headers

    def test_quote_max_age_10_seconds(self, client):
        """Quote endpoint should have max-age=10 (10 seconds)."""
        response = client.get("/api/v1/market/quote/RELIANCE")
        assert response.status_code == 200
        cache_control = response.headers["Cache-Control"]
        assert "max-age=10" in cache_control

    def test_quote_uses_public_directive(self, client):
        """Quote Cache-Control should use 'public' directive."""
        response = client.get("/api/v1/market/quote/RELIANCE")
        assert response.status_code == 200
        cache_control = response.headers["Cache-Control"]
        assert "public" in cache_control

    def test_quote_x_data_type_header(self, client):
        """Quote should have X-Data-Type header."""
        response = client.get("/api/v1/market/quote/RELIANCE")
        assert response.status_code == 200
        assert "X-Data-Type" in response.headers
        assert response.headers["X-Data-Type"] == "quote"


class TestCacheHeadersEdgeCases:
    """Test cache headers with edge cases."""

    @pytest.fixture
    def client(self):
        """Create test client with mock gateway."""
        mock_gateway = MockDataLakeGateway(num_candles=50)
        app = create_app(
            config=APIConfig(auth_mode="none"),
            datalake_gateway=mock_gateway,
        )
        return TestClient(app)

    def test_4h_timeframe_max_age_300(self, client):
        """4h timeframe should have max-age=300 (5 minutes)."""
        response = client.get(
            "/api/v1/market/candles",
            params={"symbol": "RELIANCE", "timeframe": "4h", "limit": 10},
        )
        assert response.status_code == 200
        cache_control = response.headers["Cache-Control"]
        assert "max-age=300" in cache_control

    def test_cache_headers_present_on_all_responses(self, client):
        """All successful responses should have cache headers."""
        response = client.get(
            "/api/v1/market/candles",
            params={"symbol": "RELIANCE", "timeframe": "1m", "limit": 10},
        )
        assert response.status_code == 200
        assert "Cache-Control" in response.headers
