"""Tests for BrokerGateway — delegation to connection adapters."""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from brokers.common.core.domain import Balance, Quote
from brokers.dhan.connection import DhanConnection
from brokers.dhan.domain import Order, OrderType, Position, Side
from brokers.dhan.gateway import BrokerGateway
from brokers.dhan.tests.conftest import FakeHttpClient


class TestBrokerGateway:
    """Verify that BrokerGateway delegates every call to the correct adapter."""

    def _make_gateway(self) -> tuple[BrokerGateway, DhanConnection]:
        """Create a gateway backed by a FakeHttpClient and mocked adapters."""
        client = FakeHttpClient()
        conn = DhanConnection(client=client)

        # Replace each adapter with a MagicMock so we can assert calls
        conn._market_data = MagicMock()
        conn._orders = MagicMock()
        conn._portfolio = MagicMock()

        gateway = BrokerGateway(conn)
        return gateway, conn

    # -- market data delegation ------------------------------------------

    def test_get_quote_delegates(self):
        """gateway.get_quote must call market_data.get_quote with same args."""
        gateway, conn = self._make_gateway()

        expected = Quote(symbol="RELIANCE", ltp=Decimal("2500"))
        conn._market_data.get_quote.return_value = expected

        result = gateway.quote("RELIANCE", "NSE")

        conn._market_data.get_quote.assert_called_once_with("RELIANCE", "NSE")
        assert result is expected

    # -- portfolio delegation --------------------------------------------

    def test_get_balance_delegates(self):
        """gateway.get_balance must call portfolio.get_balance."""
        gateway, conn = self._make_gateway()

        expected = Balance(available_balance=Decimal("50000"))
        conn._portfolio.get_balance.return_value = expected

        result = gateway.funds()

        conn._portfolio.get_balance.assert_called_once()
        assert result is expected

    def test_get_positions_delegates(self):
        """gateway.get_positions must call portfolio.get_positions."""
        gateway, conn = self._make_gateway()

        expected = [Position(symbol="RELIANCE", exchange="NSE", quantity=10)]
        conn._portfolio.get_positions.return_value = expected

        result = gateway.positions()

        conn._portfolio.get_positions.assert_called_once()
        assert result is expected

    # -- orders delegation -----------------------------------------------

    def test_place_order_delegates(self):
        """gateway.place_order must call orders.place_order with same kwargs."""
        gateway, conn = self._make_gateway()

        expected = Order(order_id="ORD-001", symbol="RELIANCE", exchange="NSE", side=Side.BUY, order_type=OrderType.LIMIT, quantity=10)
        conn._orders.place_order.return_value = expected

        result = gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=10,
        )

        conn._orders.place_order.assert_called_once_with(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=10,
            price=None,
            order_type="MARKET",
            trigger_price=None,
            product_type="INTRADAY",
            validity="DAY",
            correlation_id=None,
        )
        assert result is expected

    # -- lifecycle -------------------------------------------------------

    def test_close_closes_client(self):
        """gateway.close() must propagate to the underlying HTTP client."""
        client = FakeHttpClient()
        conn = DhanConnection(client=client)
        # Replace the client's close with a mock to track the call
        client.close = MagicMock()
        gateway = BrokerGateway(conn)

        gateway.close()

        client.close.assert_called_once()
