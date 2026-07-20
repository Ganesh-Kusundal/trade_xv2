"""Integration tests for post-cancellation verification (H1 Critical Fix).

Tests verify that all broker gateways properly detect race conditions where
an order was filled between cancel send and response.
"""

from unittest.mock import MagicMock

import pytest

from domain import Order, OrderResponse, OrderStatus


@pytest.fixture
def fake_client():
    from tests.support.brokers.dhan.fixtures import FakeHttpClient

    return FakeHttpClient()


@pytest.fixture
def resolver():
    from brokers.dhan.resolver import SymbolResolver

    return SymbolResolver()


class TestPaperGatewayCancelVerification:
    """Test post-cancellation verification with PaperGateway."""

    @pytest.fixture
    def paper_gateway(self):
        """Create PaperGateway without TradingContext (legacy path)."""
        from brokers.paper.paper_gateway import PaperGateway

        gw = PaperGateway()
        return gw

    def test_cancel_open_order_succeeds(self, paper_gateway):
        """Paper trading instantly fills all orders, so this test verifies
        that attempting to cancel a FILLED order correctly detects the race."""
        # Place any order (will be instantly filled in paper trading)
        place_resp = paper_gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=10,
            order_type="MARKET",
        )
        assert place_resp.success is True
        order_id = place_resp.order_id

        # Verify order is FILLED
        order = paper_gateway.get_order(order_id)
        assert order is not None
        assert order.status == OrderStatus.FILLED

        # Cancel should fail with "already filled" (race condition detected)
        cancel_resp = paper_gateway.cancel_order(order_id)
        assert cancel_resp.success is False
        assert "already filled" in cancel_resp.message.lower()
        assert cancel_resp.status == OrderStatus.FILLED

    def test_cancel_filled_order_returns_failure(self, paper_gateway):
        """Cancel a FILLED order should return ALREADY_EXECUTED error."""
        # Place a market order (instantly filled in paper trading)
        place_resp = paper_gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=10,
            order_type="MARKET",
        )
        assert place_resp.success is True
        order_id = place_resp.order_id

        # Verify order is filled
        order = paper_gateway.get_order(order_id)
        assert order is not None
        assert order.status == OrderStatus.FILLED

        # Cancel should fail with FILLED status
        cancel_resp = paper_gateway.cancel_order(order_id)
        assert cancel_resp.success is False
        assert "already filled" in cancel_resp.message.lower()
        assert cancel_resp.status == OrderStatus.FILLED

    def test_cancel_nonexistent_order_returns_failure(self, paper_gateway):
        """Cancel a non-existent order should fail gracefully."""
        cancel_resp = paper_gateway.cancel_order("NONEXISTENT-123")
        assert cancel_resp.success is False
        assert "not found" in cancel_resp.message.lower()

    def test_get_order_returns_order_if_exists(self, paper_gateway):
        """get_order should return Order if it exists."""
        place_resp = paper_gateway.place_order(
            symbol="TATASTEEL",
            exchange="NSE",
            side="BUY",
            quantity=5,
            order_type="MARKET",
        )
        order_id = place_resp.order_id

        order = paper_gateway.get_order(order_id)
        assert order is not None
        assert order.order_id == order_id
        assert order.symbol == "TATASTEEL"
        assert order.quantity == 5

    def test_get_order_returns_none_if_not_exists(self, paper_gateway):
        """get_order should return None if order doesn't exist."""
        order = paper_gateway.get_order("NONEXISTENT-999")
        assert order is None


class TestDhanGatewayCancelVerification:
    """Test post-cancellation verification with Dhan OrdersAdapter + fake HTTP."""

    def test_cancel_open_order_with_verification(self, fake_client, resolver) -> None:
        fake_client.set_response("DELETE", "/orders/DHAN-123", {"status": "success"})
        fake_client.set_response(
            "GET",
            "/orders/DHAN-123",
            {
                "data": {
                    "orderId": "DHAN-123",
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "transactionType": "BUY",
                    "quantity": 1,
                    "filledQty": 0,
                    "orderStatus": "CANCELLED",
                }
            },
        )
        from brokers.dhan.execution.orders import OrdersAdapter

        adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)
        cancel_resp = adapter.cancel_order("DHAN-123")
        assert cancel_resp.success is True

    def test_cancel_filled_order_detects_race_condition(self, fake_client, resolver) -> None:
        fake_client.set_response("DELETE", "/orders/DHAN-456", {"status": "success"})
        fake_client.set_response(
            "GET",
            "/orders/DHAN-456",
            {
                "data": {
                    "orderId": "DHAN-456",
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "transactionType": "BUY",
                    "quantity": 1,
                    "filledQty": 1,
                    "orderStatus": "TRADED",
                }
            },
        )
        from brokers.dhan.execution.orders import OrdersAdapter

        adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)
        cancel_resp = adapter.cancel_order("DHAN-456")
        assert cancel_resp.success is False
        assert "already filled" in (cancel_resp.message or "").lower()
        assert cancel_resp.status == OrderStatus.FILLED

    def test_get_order_returns_order_from_direct_lookup(self, fake_client, resolver) -> None:
        from tests.unit.brokers.dhan.test_gateway_get_order import (
            _make_gateway_with_real_adapter,
        )

        fake_client.set_response(
            "GET",
            "/orders/DHAN-222",
            {
                "data": {
                    "orderId": "DHAN-222",
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "transactionType": "BUY",
                    "quantity": 1,
                    "filledQty": 0,
                    "orderStatus": "PENDING",
                }
            },
        )
        gw = _make_gateway_with_real_adapter(fake_client, resolver)
        order = gw.get_order("DHAN-222")
        assert order is not None
        assert order.order_id == "DHAN-222"

    def test_get_order_raises_when_not_found(self, fake_client, resolver) -> None:
        from domain.errors import OrderError
        from tests.unit.brokers.dhan.test_gateway_get_order import (
            _make_gateway_with_real_adapter,
        )

        fake_client.set_side_effect("GET", "/orders/DHAN-999", RuntimeError("not found"))
        gw = _make_gateway_with_real_adapter(fake_client, resolver)
        with pytest.raises(OrderError):
            gw.get_order("DHAN-999")


class TestUpstoxGatewayCancelVerification:
    """Test post-cancellation verification with Upstox gateway (mocked)."""

    @pytest.fixture
    def mock_upstox_gateway(self):
        """Create Upstox gateway with mocked broker and order command."""
        from brokers.upstox.broker import UpstoxBroker
        from brokers.upstox.wire import UpstoxBrokerGateway

        # Mock settings directly
        mock_settings = MagicMock()
        mock_settings.analytics_only = False
        mock_settings.allow_live_orders = True

        mock_broker = MagicMock(spec=UpstoxBroker)
        mock_broker.settings = mock_settings

        mock_order_cmd = MagicMock()

        gw = UpstoxBrokerGateway.__new__(UpstoxBrokerGateway)
        gw._broker = mock_broker
        gw._order_command = mock_order_cmd
        gw._market_data_adapter = MagicMock()
        gw._stream_manager = MagicMock()
        # Wire the OrderGateway delegate that cancel_order() uses
        gw._order_gw = MagicMock()
        gw._order_gw.cancel_order = mock_order_cmd.cancel_order
        gw._order_gw.get_order = MagicMock(return_value=None)

        return gw, mock_order_cmd

    def test_cancel_open_order_with_verification(self, mock_upstox_gateway):
        """Cancel OPEN order should succeed after verification."""
        gw, mock_order_cmd = mock_upstox_gateway

        # Mock cancel_order to return success
        mock_order_cmd.cancel_order.return_value = OrderResponse.ok(
            order_id="UPSTOX-123",
            message="Cancel request accepted",
        )

        # Mock get_orderbook to return cancelled order
        mock_order = MagicMock(spec=Order)
        mock_order.order_id = "UPSTOX-123"
        mock_order.status = OrderStatus.CANCELLED
        gw.get_orderbook = MagicMock(return_value=[mock_order])

        cancel_resp = gw.cancel_order("UPSTOX-123")
        assert cancel_resp.success is True

    def test_cancel_filled_order_detects_race_condition(self, mock_upstox_gateway):
        """Cancel should detect if order was FILLED before cancel completed."""
        gw, mock_order_cmd = mock_upstox_gateway

        # Mock cancel_order to return success
        mock_order_cmd.cancel_order.return_value = OrderResponse.ok(
            order_id="UPSTOX-456",
            message="Cancel request accepted",
        )

        # Mock get_orderbook to show order was FILLED (race condition)
        mock_order = MagicMock(spec=Order)
        mock_order.order_id = "UPSTOX-456"
        mock_order.status = OrderStatus.FILLED
        gw.get_orderbook = MagicMock(return_value=[mock_order])

        cancel_resp = gw.cancel_order("UPSTOX-456")

        # Should fail because order was already filled
        assert cancel_resp.success is False
        assert "already filled" in cancel_resp.message.lower()
        assert cancel_resp.status == OrderStatus.FILLED

    def test_analytics_only_mode_blocks_cancel(self, mock_upstox_gateway):
        """Cancel should be blocked in analytics-only mode."""
        gw, _mock_order_cmd = mock_upstox_gateway
        gw._broker.settings.analytics_only = True

        cancel_resp = gw.cancel_order("UPSTOX-789")
        assert cancel_resp.success is False
        assert "analytics-only" in cancel_resp.message.lower()


class TestCancelVerificationEdgeCases:
    """Test edge cases in post-cancellation verification."""

    @pytest.fixture
    def paper_gateway(self):
        """Create PaperGateway without TradingContext (legacy path)."""
        from brokers.paper.paper_gateway import PaperGateway

        gw = PaperGateway()
        return gw

    def test_cancel_partially_filled_order(self, paper_gateway):
        """Paper trading instantly fills all orders, verifying race condition
        detection works correctly."""
        place_resp = paper_gateway.place_order(
            symbol="INFY",
            exchange="NSE",
            side="BUY",
            quantity=10,
            order_type="MARKET",
        )

        # Order is already filled
        cancel_resp = paper_gateway.cancel_order(place_resp.order_id)
        assert cancel_resp.success is False
        assert "already filled" in cancel_resp.message.lower()

    def test_multiple_cancel_attempts_same_order(self, paper_gateway):
        """Multiple cancel attempts on same FILLED order should be consistent."""
        place_resp = paper_gateway.place_order(
            symbol="HDFCBANK",
            exchange="NSE",
            side="BUY",
            quantity=10,
            order_type="MARKET",
        )
        order_id = place_resp.order_id

        # First cancel should fail (already filled)
        cancel_resp1 = paper_gateway.cancel_order(order_id)
        assert cancel_resp1.success is False
        assert "already filled" in cancel_resp1.message.lower()

        # Second cancel should also fail consistently
        cancel_resp2 = paper_gateway.cancel_order(order_id)
        assert cancel_resp2.success is False

    def test_cancel_orderbook_order_not_in_list(self, paper_gateway):
        """Cancel when orderbook returns empty should fail gracefully."""
        # Place order
        place_resp = paper_gateway.place_order(
            symbol="ICICIBANK",
            exchange="NSE",
            side="BUY",
            quantity=10,
            order_type="MARKET",
        )
        order_id = place_resp.order_id

        # Manually clear orderbook (simulate edge case)
        paper_gateway._orders._orders.clear()

        # Cancel should fail
        cancel_resp = paper_gateway.cancel_order(order_id)
        assert cancel_resp.success is False
