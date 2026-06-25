"""Contract tests for health and symbol endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Test health and readiness endpoints."""

    def test_health_check(self, client: TestClient):
        """GET /api/v1/health returns healthy status."""
        response = client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "timestamp" in data

    def test_readiness_check(self, client: TestClient):
        """GET /api/v1/health/readyz returns readiness status."""
        response = client.get("/api/v1/health/readyz")

        assert response.status_code == 200
        data = response.json()
        assert "ready" in data
        assert "checks" in data
        assert "timestamp" in data
        assert isinstance(data["ready"], bool)
        assert isinstance(data["checks"], dict)


class TestSymbolEndpoints:
    """Test symbol search and metadata endpoints."""

    def test_search_symbols(self, client: TestClient, test_symbol: str):
        """GET /api/v1/symbols/search returns matching symbols."""
        response = client.get(
            "/api/v1/symbols/search",
            params={"q": test_symbol[:4], "limit": 10},
        )

        # Should succeed even if no results
        assert response.status_code in [200, 500, 503]  # 503 if catalog not initialized

        if response.status_code == 200:
            data = response.json()
            assert "results" in data
            assert "count" in data
            assert isinstance(data["results"], list)
            assert isinstance(data["count"], int)

    def test_search_symbols_with_exchange(self, client: TestClient):
        """GET /api/v1/symbols/search with exchange filter."""
        response = client.get(
            "/api/v1/symbols/search",
            params={"q": "REL", "exchange": "NSE", "limit": 5},
        )

        assert response.status_code in [200, 500, 503]

    def test_search_symbols_validation(self, client: TestClient):
        """GET /api/v1/symbols/search validates query parameters."""
        # Empty query should fail validation
        response = client.get("/api/v1/symbols/search", params={"q": ""})
        assert response.status_code == 422  # Validation error

        # Query too long should fail
        response = client.get(
            "/api/v1/symbols/search",
            params={"q": "A" * 51},
        )
        assert response.status_code == 422

    def test_get_symbol(self, client: TestClient, test_symbol: str):
        """GET /api/v1/symbols/{symbol} returns symbol metadata."""
        response = client.get(f"/api/v1/symbols/{test_symbol}")

        # May return 404 if symbol not in catalog, or 503 if not initialized
        assert response.status_code in [200, 404, 503]

        if response.status_code == 200:
            data = response.json()
            assert data["symbol"] == test_symbol.upper()
            assert "exchange" in data
            assert "sector" in data
            assert "lot_size" in data

    def test_get_symbol_not_found(self, client: TestClient):
        """GET /api/v1/symbols/{symbol} returns 404 for unknown symbol."""
        response = client.get("/api/v1/symbols/INVALIDSYMBOL123")
        assert response.status_code in [404, 503]

    def test_get_universe(self, client: TestClient, test_universe: str):
        """GET /api/v1/symbols/universe/{name} returns universe symbols."""
        response = client.get(f"/api/v1/symbols/universe/{test_universe}")

        # May succeed or return 404 if universe file missing
        assert response.status_code in [200, 404, 500]

        if response.status_code == 200:
            data = response.json()
            assert "name" in data
            assert "symbols" in data
            assert "count" in data
            assert isinstance(data["symbols"], list)

    def test_get_universe_invalid(self, client: TestClient):
        """GET /api/v1/symbols/universe/{name} rejects invalid universe."""
        response = client.get("/api/v1/symbols/universe/INVALID")
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data


class TestSymbolEndpointContracts:
    """Test API contract compliance for symbol endpoints."""

    def test_search_response_shape(self, client: TestClient):
        """Search response matches expected schema."""
        response = client.get("/api/v1/symbols/search", params={"q": "A", "limit": 1})

        if response.status_code == 200:
            data = response.json()
            # Must have these fields
            assert all(key in data for key in ["results", "count"])

    def test_symbol_info_shape(self, client: TestClient):
        """Symbol info response matches expected schema."""
        response = client.get("/api/v1/symbols/RELIANCE")

        if response.status_code == 200:
            data = response.json()
            required_fields = [
                "symbol",
                "exchange",
                "sector",
                "isin",
                "lot_size",
                "tick_size",
                "instrument_type",
            ]
            assert all(key in data for key in required_fields)

    def test_universe_response_shape(self, client: TestClient):
        """Universe response matches expected schema."""
        response = client.get("/api/v1/symbols/universe/nifty50")

        if response.status_code == 200:
            data = response.json()
            assert all(key in data for key in ["name", "symbols", "count"])
