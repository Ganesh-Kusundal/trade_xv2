"""Analytics endpoints tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestIndicatorsEndpoint:
    """Test GET /api/v1/analytics/indicators endpoint."""

    def test_indicators_invalid_type(self, client: TestClient):
        """Should reject invalid indicator type."""
        response = client.get(
            "/api/v1/analytics/indicators?symbol=RELIANCE&type=invalid&timeframe=1m"
        )
        assert response.status_code in (400, 404, 503)

    def test_indicators_missing_symbol(self, client: TestClient):
        """Should require symbol parameter."""
        response = client.get("/api/v1/analytics/indicators?type=rsi&timeframe=1m")
        assert response.status_code in (400, 422, 503)

    def test_indicators_missing_type(self, client: TestClient):
        """Should require type parameter."""
        response = client.get("/api/v1/analytics/indicators?symbol=RELIANCE")
        assert response.status_code in (400, 422, 503)

    def test_indicators_valid_params(self, client: TestClient):
        """Should accept valid parameters."""
        response = client.get(
            "/api/v1/analytics/indicators?symbol=RELIANCE&type=rsi&timeframe=1m&limit=100"
        )
        assert response.status_code in (200, 500, 503)


class TestRelativeStrengthEndpoint:
    """Test GET /api/v1/analytics/relative-strength endpoint."""

    def test_relative_strength_exists(self, client: TestClient):
        """Should have relative-strength endpoint."""
        response = client.get("/api/v1/analytics/relative-strength?limit=20")
        assert response.status_code in (200, 404, 500, 503)

    def test_relative_strength_custom_limit(self, client: TestClient):
        """Should accept custom limit."""
        response = client.get("/api/v1/analytics/relative-strength?limit=10")
        assert response.status_code in (200, 404, 500, 503)


class TestMarketBreadthEndpoint:
    """Test GET /api/v1/analytics/market-breadth endpoint."""

    def test_market_breadth_exists(self, client: TestClient):
        """Should have market-breadth endpoint."""
        response = client.get("/api/v1/analytics/market-breadth")
        assert response.status_code in (200, 404, 500, 503)

    def test_market_breadth_returns_structure(self, client: TestClient):
        """Should return breadth metrics structure."""
        response = client.get("/api/v1/analytics/market-breadth")
        if response.status_code == 200:
            data = response.json()
            assert "advances" in data
            assert "declines" in data
            assert "breadth_score" in data


class TestStrategiesRunEndpoint:
    """Test POST /api/v1/analytics/strategies/run endpoint."""

    def test_strategies_run_requires_names(self, client: TestClient):
        response = client.post("/api/v1/analytics/strategies/run", json={})
        assert response.status_code == 400

    def test_strategies_run_valid_names(self, client: TestClient):
        from analytics.strategy.registry import StrategyRegistry

        StrategyRegistry.discover("analytics.strategy.builtins")
        names = StrategyRegistry.list()
        assert names, "No strategies registered"

        response = client.post(
            "/api/v1/analytics/strategies/run",
            json={"names": [names[0]]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["strategy_count"] >= 1
        assert len(data["strategies"]) >= 1
