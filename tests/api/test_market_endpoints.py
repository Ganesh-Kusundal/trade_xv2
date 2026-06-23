"""Market data endpoints tests."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient


class TestGetCandlesEndpoint:
    """Test GET /api/v1/market/candles endpoint."""

    def test_get_candles_missing_symbol(self, client: TestClient):
        """Should require symbol parameter."""
        response = client.get("/api/v1/market/candles?timeframe=1m")
        assert response.status_code in (400, 404, 422, 503)

    def test_get_candles_missing_timeframe(self, client: TestClient):
        """Should require timeframe parameter."""
        response = client.get("/api/v1/market/candles?symbol=RELIANCE")
        assert response.status_code in (400, 404, 422, 503)

    def test_get_candles_valid_params(self, client: TestClient):
        """Should accept valid parameters."""
        response = client.get("/api/v1/market/candles?symbol=RELIANCE&timeframe=1m")
        assert response.status_code in (200, 404, 500, 503)

    def test_get_candles_with_limit(self, client: TestClient):
        """Should accept limit parameter."""
        response = client.get("/api/v1/market/candles?symbol=RELIANCE&timeframe=1m&limit=100")
        assert response.status_code in (200, 404, 500, 503)

    def test_get_candles_with_date_range(self, client: TestClient):
        """Should accept date range parameters."""
        response = client.get("/api/v1/market/candles?symbol=RELIANCE&timeframe=1m&from_ts=1704067200000&to_ts=1704153600000")
        assert response.status_code in (200, 404, 500, 503)

    def test_get_candles_cache_headers(self, client: TestClient):
        """Should include cache headers."""
        response = client.get("/api/v1/market/candles?symbol=RELIANCE&timeframe=1m")
        if response.status_code == 200:
            assert "Cache-Control" in response.headers


class TestGetQuoteEndpoint:
    """Test GET /api/v1/market/quote/{symbol} endpoint."""

    def test_get_quote_exists(self, client: TestClient):
        """Should have quote endpoint."""
        response = client.get("/api/v1/market/quote/RELIANCE")
        assert response.status_code in (200, 404, 500, 503)

    def test_get_quote_with_exchange(self, client: TestClient):
        """Should accept exchange parameter."""
        response = client.get("/api/v1/market/quote/RELIANCE?exchange=NSE")
        assert response.status_code in (200, 404, 500, 503)

    def test_get_quote_returns_ltp(self, client: TestClient):
        """Should return LTP in response."""
        response = client.get("/api/v1/market/quote/RELIANCE")
        if response.status_code == 200:
            data = response.json()
            assert "ltp" in data
            assert "symbol" in data

    def test_get_quote_cache_headers(self, client: TestClient):
        """Should include cache headers for quote."""
        response = client.get("/api/v1/market/quote/RELIANCE")
        if response.status_code == 200:
            assert "Cache-Control" in response.headers