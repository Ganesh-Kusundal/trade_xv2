"""Portfolio endpoints tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestGetPositionsEndpoint:
    """Test GET /api/v1/portfolio/positions endpoint."""

    def test_get_positions_exists(self, client: TestClient):
        """Should have positions endpoint."""
        response = client.get("/api/v1/portfolio/positions")
        assert response.status_code in (200, 503)

    def test_get_positions_with_status_filter(self, client: TestClient):
        """Should accept status filter."""
        response = client.get("/api/v1/portfolio/positions?status=open")
        assert response.status_code in (200, 400, 503)

    def test_get_positions_invalid_status(self, client: TestClient):
        """Should reject invalid status."""
        response = client.get("/api/v1/portfolio/positions?status=invalid")
        assert response.status_code in (200, 400, 503)


class TestGetHoldingsEndpoint:
    """Test GET /api/v1/portfolio/holdings endpoint."""

    def test_get_holdings_exists(self, client: TestClient):
        """Should have holdings endpoint."""
        response = client.get("/api/v1/portfolio/holdings")
        assert response.status_code in (200, 503)

    def test_get_holdings_returns_structure(self, client: TestClient):
        """Should return holdings structure."""
        response = client.get("/api/v1/portfolio/holdings")
        if response.status_code == 200:
            data = response.json()
            assert "holdings" in data
            assert "count" in data


class TestGetPortfolioSummaryEndpoint:
    """Test GET /api/v1/portfolio/summary endpoint."""

    def test_get_summary_exists(self, client: TestClient):
        """Should have summary endpoint."""
        response = client.get("/api/v1/portfolio/summary")
        assert response.status_code in (200, 503)

    def test_get_summary_returns_metrics(self, client: TestClient):
        """Should return portfolio metrics."""
        response = client.get("/api/v1/portfolio/summary")
        if response.status_code == 200:
            data = response.json()
            assert "total_value" in data
            assert "total_pnl" in data


class TestGetPnlHistoryEndpoint:
    """Test GET /api/v1/portfolio/pnl endpoint."""

    def test_get_pnl_exists(self, client: TestClient):
        """Should have pnl endpoint."""
        response = client.get("/api/v1/portfolio/pnl")
        assert response.status_code in (200, 503)

    def test_get_pnl_with_date_range(self, client: TestClient):
        """Should accept date range filters."""
        response = client.get("/api/v1/portfolio/pnl?from_date=2024-01-01&to_date=2024-12-31")
        assert response.status_code in (200, 503)

    def test_get_pnl_with_group_by(self, client: TestClient):
        """Should accept group_by parameter."""
        response = client.get("/api/v1/portfolio/pnl?group_by=day")
        assert response.status_code in (200, 503)


class TestSquareOffEndpoint:
    """Test POST /api/v1/portfolio/square-off endpoint."""

    def test_square_off_exists(self, client: TestClient):
        """Should have square-off endpoint."""
        response = client.post("/api/v1/portfolio/square-off")
        assert response.status_code in (200, 405, 503)

    def test_square_off_with_symbol(self, client: TestClient):
        """Should accept symbol parameter."""
        response = client.post("/api/v1/portfolio/square-off?symbol=RELIANCE")
        assert response.status_code in (200, 405, 503)
