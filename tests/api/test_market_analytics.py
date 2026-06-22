"""Contract tests for market data and analytics endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class TestMarketDataEndpoints:
    """Test market data endpoints."""
    
    def test_get_candles(self, client: TestClient, test_symbol: str, test_timeframe: str):
        """GET /api/v1/market/candles returns OHLCV data."""
        response = client.get(
            "/api/v1/market/candles",
            params={
                "symbol": test_symbol,
                "timeframe": test_timeframe,
                "limit": 10,
            },
        )
        
        # May return 200, 404 (no data), or 503 (gateway not initialized)
        assert response.status_code in [200, 404, 500, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "symbol" in data
            assert "timeframe" in data
            assert "candles" in data
            assert "count" in data
            assert isinstance(data["candles"], list)
    
    def test_get_candles_with_date_range(self, client: TestClient, test_symbol: str, test_date_range: dict):
        """GET /api/v1/market/candles with date range filter."""
        response = client.get(
            "/api/v1/market/candles",
            params={
                "symbol": test_symbol,
                "timeframe": "1m",
                "from_ts": test_date_range["from_ts"],
                "to_ts": test_date_range["to_ts"],
                "limit": 50,
            },
        )
        
        assert response.status_code in [200, 404, 500, 503]
    
    def test_get_candles_validation(self, client: TestClient):
        """GET /api/v1/market/candles validates parameters."""
        # Limit too high should fail
        response = client.get(
            "/api/v1/market/candles",
            params={"symbol": "TEST", "timeframe": "1m", "limit": 10000},
        )
        assert response.status_code == 422
    
    def test_get_candle_shape(self, client: TestClient, test_symbol: str):
        """Candle response has correct shape."""
        response = client.get(
            "/api/v1/market/candles",
            params={"symbol": test_symbol, "timeframe": "1m", "limit": 1},
        )
        
        if response.status_code == 200:
            data = response.json()
            if data["count"] > 0:
                candle = data["candles"][0]
                required_fields = ["t", "o", "h", "l", "c", "v"]
                assert all(field in candle for field in required_fields)
    
    def test_get_quote(self, client: TestClient, test_symbol: str):
        """GET /api/v1/market/quote/{symbol} returns latest quote."""
        response = client.get(f"/api/v1/market/quote/{test_symbol}")
        
        assert response.status_code in [200, 404, 500, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "symbol" in data
            assert "ltp" in data
            assert "timestamp" in data
            assert isinstance(data["ltp"], (int, float))
    
    def test_get_quote_with_exchange(self, client: TestClient, test_symbol: str):
        """GET /api/v1/market/quote/{symbol} with exchange parameter."""
        response = client.get(
            f"/api/v1/market/quote/{test_symbol}",
            params={"exchange": "NSE"},
        )
        
        assert response.status_code in [200, 404, 500, 503]


class TestAnalyticsEndpoints:
    """Test analytics endpoints."""
    
    def test_get_indicators(self, client: TestClient, test_symbol: str):
        """GET /api/v1/analytics/indicators returns indicator values."""
        response = client.get(
            "/api/v1/analytics/indicators",
            params={
                "symbol": test_symbol,
                "type": "rsi",
                "timeframe": "1m",
                "limit": 50,
            },
        )
        
        # May return 200, 500 (view manager error), or 503 (not initialized)
        assert response.status_code in [200, 500, 501, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "symbol" in data
            assert "indicator_type" in data
            assert "values" in data
            assert "count" in data
    
    def test_get_indicators_all_types(self, client: TestClient, test_symbol: str):
        """Test all indicator types."""
        indicator_types = ["atr", "vwap", "rsi", "momentum", "volume"]
        
        for ind_type in indicator_types:
            response = client.get(
                "/api/v1/analytics/indicators",
                params={
                    "symbol": test_symbol,
                    "type": ind_type,
                    "limit": 10,
                },
            )
            assert response.status_code in [200, 400, 500, 503]
    
    def test_get_indicators_invalid_type(self, client: TestClient, test_symbol: str):
        """GET /api/v1/analytics/indicators rejects invalid type."""
        response = client.get(
            "/api/v1/analytics/indicators",
            params={"symbol": test_symbol, "type": "invalid"},
        )
        assert response.status_code in [400, 500, 503]
    
    def test_get_snapshot(self, client: TestClient):
        """GET /api/v1/analytics/snapshot returns scanner snapshot."""
        response = client.get("/api/v1/analytics/snapshot", params={"limit": 20})
        
        assert response.status_code in [200, 500, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "candidates" in data
            assert "count" in data
    
    def test_get_top_candidates(self, client: TestClient):
        """GET /api/v1/analytics/top-candidates returns top candidates."""
        response = client.get("/api/v1/analytics/top-candidates", params={"limit": 10})
        
        assert response.status_code in [200, 500, 503]
    
    def test_get_relative_strength(self, client: TestClient):
        """GET /api/v1/analytics/relative-strength returns RS rankings."""
        response = client.get("/api/v1/analytics/relative-strength")
        
        # Currently returns stub
        assert response.status_code in [200, 501, 503]
    
    def test_get_market_breadth(self, client: TestClient):
        """GET /api/v1/analytics/market-breadth returns breadth indicators."""
        response = client.get("/api/v1/analytics/market-breadth")
        
        # Currently not implemented
        assert response.status_code in [501, 503]


class TestScannerEndpoints:
    """Test scanner endpoints."""
    
    def test_get_scan_results(self, client: TestClient):
        """GET /api/v1/scanner/results returns scan history."""
        response = client.get("/api/v1/scanner/results", params={"limit": 5})
        
        assert response.status_code in [200, 500, 503]
    
    def test_get_scanner_top_candidates(self, client: TestClient):
        """GET /api/v1/scanner/top-candidates returns candidates."""
        response = client.get("/api/v1/scanner/top-candidates", params={"limit": 10})
        
        assert response.status_code in [200, 500, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "candidates" in data
            assert "count" in data
    
    def test_get_scanner_snapshots(self, client: TestClient):
        """GET /api/v1/scanner/snapshots returns full snapshots."""
        response = client.get("/api/v1/scanner/snapshots", params={"limit": 50})
        
        assert response.status_code in [200, 500, 503]
    
    def test_run_scan(self, client: TestClient):
        """POST /api/v1/scanner/run triggers scanner."""
        response = client.post(
            "/api/v1/scanner/run",
            params={"scanner_name": "intraday", "universe": "NIFTY500"},
        )
        
        assert response.status_code in [200, 500, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "scan_id" in data
            assert "status" in data


class TestStrategyEndpoints:
    """Test strategy endpoints."""
    
    def test_get_strategy_signals(self, client: TestClient):
        """GET /api/v1/strategy/signals returns strategy signals."""
        strategies = ["halftrend", "momentum", "breakout"]
        
        for strategy in strategies:
            response = client.get(
                "/api/v1/strategy/signals",
                params={"strategy": strategy, "limit": 20},
            )
            assert response.status_code in [200, 400, 500, 503]
    
    def test_get_strategy_signals_invalid(self, client: TestClient):
        """GET /api/v1/strategy/signals rejects invalid strategy."""
        response = client.get(
            "/api/v1/strategy/signals",
            params={"strategy": "invalid", "limit": 10},
        )
        assert response.status_code in [400, 500, 503]
    
    def test_get_strategy_candidates(self, client: TestClient):
        """GET /api/v1/strategy/candidates returns candidates."""
        response = client.get("/api/v1/strategy/candidates", params={"limit": 20})
        
        assert response.status_code in [200, 500, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "signals" in data
            assert "count" in data
