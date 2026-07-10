"""Contract tests for portfolio and orders endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestPortfolioEndpoints:
    """Test portfolio management endpoints."""

    def test_get_positions(self, client: TestClient):
        """GET /api/v1/portfolio/positions returns positions."""
        response = client.get("/api/v1/portfolio/positions")

        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "positions" in data
            assert "count" in data
            assert "total_pnl" in data

    def test_get_positions_with_filter(self, client: TestClient):
        """GET /api/v1/portfolio/positions with status filter."""
        for status in ["open", "closed", "all"]:
            response = client.get(
                "/api/v1/portfolio/positions",
                params={"status": status},
            )
            assert response.status_code in [200, 503]

    def test_get_holdings(self, client: TestClient):
        """GET /api/v1/portfolio/holdings returns holdings."""
        response = client.get("/api/v1/portfolio/holdings")

        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "holdings" in data
            assert "count" in data
            assert "total_value" in data

    def test_get_portfolio_summary(self, client: TestClient):
        """GET /api/v1/portfolio/summary returns portfolio metrics."""
        response = client.get("/api/v1/portfolio/summary")

        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            required_fields = [
                "total_value",
                "total_invested",
                "total_pnl",
                "total_pnl_percent",
                "margin_used",
                "margin_available",
            ]
            assert all(field in data for field in required_fields)

    def test_get_pnl_history(self, client: TestClient):
        """GET /api/v1/portfolio/pnl returns P&L history."""
        response = client.get(
            "/api/v1/portfolio/pnl",
            params={
                "from_date": "2024-01-01",
                "to_date": "2024-01-31",
                "group_by": "day",
            },
        )

        assert response.status_code in [200, 503]

    def test_square_off_positions(self, client: TestClient):
        """POST /api/v1/portfolio/square-off closes positions."""
        # Square off all
        response = client.post("/api/v1/portfolio/square-off")
        assert response.status_code in [200, 503]

        # Square off specific symbol
        response = client.post(
            "/api/v1/portfolio/square-off",
            params={"symbol": "RELIANCE"},
        )
        assert response.status_code in [200, 503]


class TestOrdersEndpoints:
    """Test order management endpoints."""

    def test_get_orders(self, client: TestClient):
        """GET /api/v1/orders returns order history."""
        response = client.get("/api/v1/orders", params={"limit": 20})

        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "orders" in data
            assert "count" in data

    def test_get_orders_with_filters(self, client: TestClient):
        """GET /api/v1/orders with status and date filters."""
        response = client.get(
            "/api/v1/orders",
            params={
                "status": "complete",
                "from_date": "2024-01-01",
                "to_date": "2024-01-31",
                "limit": 50,
            },
        )
        assert response.status_code in [200, 503]

    def test_get_order(self, client: TestClient):
        """GET /api/v1/orders/{order_id} returns order details."""
        response = client.get("/api/v1/orders/ORD_001")
        assert response.status_code in [404, 503]

    def test_place_order(self, client: TestClient):
        """POST /api/v1/orders places new order."""
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "transaction_type": "BUY",
            "order_type": "MARKET",
            "quantity": 1,
            "product_type": "INTRADAY",
        }

        response = client.post("/api/v1/orders", json=order_data)
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "order_id" in data
            assert "status" in data

    def test_place_limit_order(self, client: TestClient):
        """POST /api/v1/orders places limit order."""
        order_data = {
            "symbol": "TCS",
            "exchange": "NSE",
            "transaction_type": "BUY",
            "order_type": "LIMIT",
            "quantity": 1,
            "price": 3500.00,
            "product_type": "DELIVERY",
        }

        response = client.post("/api/v1/orders", json=order_data)
        assert response.status_code in [200, 503]

    def test_place_sl_order(self, client: TestClient):
        """POST /api/v1/orders places stop-loss order."""
        order_data = {
            "symbol": "INFY",
            "exchange": "NSE",
            "transaction_type": "SELL",
            "order_type": "SL",
            "quantity": 1,
            "price": 1450.00,
            "trigger_price": 1445.00,
            "product_type": "INTRADAY",
        }

        response = client.post("/api/v1/orders", json=order_data)
        assert response.status_code in [200, 503]

    def test_modify_order(self, client: TestClient):
        """PUT /api/v1/orders/{order_id} modifies order."""
        order_data = {
            "symbol": "HDFC",
            "exchange": "NSE",
            "transaction_type": "BUY",
            "order_type": "LIMIT",
            "quantity": 2,
            "price": 1600.00,
        }

        response = client.put("/api/v1/orders/ORD_001", json=order_data)
        assert response.status_code in [200, 404, 503]

    def test_cancel_order(self, client: TestClient):
        """DELETE /api/v1/orders/{order_id} cancels order."""
        response = client.delete("/api/v1/orders/ORD_001")
        assert response.status_code in [200, 404, 503]

    def test_get_trades(self, client: TestClient):
        """GET /api/v1/orders/trades returns trade executions."""
        response = client.get("/api/v1/orders/trades", params={"limit": 20})

        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "trades" in data
            assert "count" in data

    def test_get_tradebook(self, client: TestClient):
        """GET /api/v1/orders/tradebook returns complete tradebook."""
        response = client.get(
            "/api/v1/orders/tradebook",
            params={"from_date": "2024-01-01", "to_date": "2024-01-31"},
        )

        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "trades" in data
            assert "total_trades" in data
            assert "win_rate" in data


class TestOrderValidation:
    """Test order validation and error handling."""

    def test_place_order_invalid_quantity(self, client: TestClient):
        """POST /api/v1/orders rejects zero quantity."""
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "transaction_type": "BUY",
            "order_type": "MARKET",
            "quantity": 0,
            "product_type": "INTRADAY",
        }

        response = client.post("/api/v1/orders", json=order_data)
        assert response.status_code in [422, 503]

    def test_place_order_missing_fields(self, client: TestClient):
        """POST /api/v1/orders rejects incomplete data."""
        incomplete_data = {
            "symbol": "RELIANCE",
            "transaction_type": "BUY",
        }

        response = client.post("/api/v1/orders", json=incomplete_data)
        assert response.status_code in [422, 503]

    def test_place_order_invalid_transaction_type(self, client: TestClient):
        """POST /api/v1/orders rejects invalid transaction type."""
        order_data = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "transaction_type": "INVALID",
            "order_type": "MARKET",
            "quantity": 1,
            "product_type": "INTRADAY",
        }

        response = client.post("/api/v1/orders", json=order_data)
        assert response.status_code in [422, 503]
