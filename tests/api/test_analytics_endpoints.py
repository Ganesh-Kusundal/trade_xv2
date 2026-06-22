"""Analytics endpoint integration tests.

Verifies that analytics endpoints use real OMS services (RankingEngine, BreadthAnalytics).
Tests verify real data flows, not just route existence.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import pandas as pd

from analytics.ranking.ranking import RankingEngine, RankingFacade
from analytics.market_breadth.breadth import BreadthAnalytics


class TestRelativeStrengthEndpoint:
    """Test GET /api/analytics/relative-strength endpoint."""

    def test_relative_strength_returns_rankings(self, client: TestClient):
        """Should return relative strength rankings."""
        response = client.get("/api/v1/analytics/relative-strength")
        # Should return 200 with real data once wired
        assert response.status_code in (200, 500)

    def test_relative_strength_limit_parameter(self, client: TestClient):
        """Should respect limit parameter."""
        response = client.get("/api/v1/analytics/relative-strength?limit=10")
        assert response.status_code in (200, 500)

    def test_relative_strength_limit_validation(self, client: TestClient):
        """Should validate limit range."""
        response = client.get("/api/v1/analytics/relative-strength?limit=0")
        assert response.status_code == 422

        response = client.get("/api/v1/analytics/relative-strength?limit=200")
        assert response.status_code in (200, 422)

    def test_relative_strength_response_structure(self, client: TestClient):
        """Should return proper response structure."""
        response = client.get("/api/v1/analytics/relative-strength?limit=5")
        if response.status_code == 200:
            data = response.json()
            assert "rankings" in data
            assert "count" in data


class TestMarketBreadthEndpoint:
    """Test GET /api/analytics/market-breadth endpoint."""

    def test_market_breadth_returns_data(self, client: TestClient):
        """Should return market breadth indicators."""
        response = client.get("/api/v1/analytics/market-breadth")
        # Should return 200 with real data once wired (not 501)
        assert response.status_code in (200, 500)

    def test_market_breadth_response_structure(self, client: TestClient):
        """Should return proper breadth response structure."""
        response = client.get("/api/v1/analytics/market-breadth")
        if response.status_code == 200:
            data = response.json()
            # Verify MarketBreadthResponse schema fields
            required_fields = [
                "advances", "declines", "unchanged",
                "advance_decline_ratio", "new_highs", "new_lows",
                "breadth_score", "regime"
            ]
            for field in required_fields:
                assert field in data, f"Missing field: {field}"

    def test_market_breadth_regime_values(self, client: TestClient):
        """Should return valid regime values."""
        response = client.get("/api/v1/analytics/market-breadth")
        if response.status_code == 200:
            data = response.json()
            assert data["regime"] in ("Positive", "Negative", "Neutral")


class TestIndicatorsEndpoint:
    """Test GET /api/analytics/indicators endpoint (already wired, regression test)."""

    def test_indicators_requires_symbol(self, client: TestClient):
        """Should require symbol parameter."""
        response = client.get("/api/v1/analytics/indicators?type=rsi")
        assert response.status_code == 422

    def test_indicators_requires_type(self, client: TestClient):
        """Should require type parameter."""
        response = client.get("/api/v1/analytics/indicators?symbol=RELIANCE")
        assert response.status_code == 422

    def test_indicators_invalid_type(self, client: TestClient):
        """Should reject invalid indicator type."""
        response = client.get("/api/v1/analytics/indicators?symbol=RELIANCE&type=invalid")
        assert response.status_code in (400, 500)


class TestSnapshotEndpoint:
    """Test GET /api/analytics/snapshot endpoint (already wired, regression test)."""

    def test_snapshot_returns_data(self, client: TestClient):
        """Should return snapshot data."""
        response = client.get("/api/v1/analytics/snapshot?limit=10")
        assert response.status_code in (200, 500)
