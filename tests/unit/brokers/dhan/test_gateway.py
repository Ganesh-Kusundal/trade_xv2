"""Tests for DhanWireAdapter — delegation to connection adapters."""

from __future__ import annotations

from tests.support.order_request_factory import make_order_request as _order_request

import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from domain.entities import Position
from brokers.providers.dhan.streaming.connection import DhanConnection
from brokers.providers.dhan.wire import DhanWireAdapter
from domain import Balance, OrderRequest, Quote
from tests.support.brokers.dhan.fixtures import FakeHttpClient


class TestBrokerGateway:
    """Verify that DhanWireAdapter delegates every call to the correct adapter."""

    def _make_gateway(self) -> tuple[DhanWireAdapter, DhanConnection]:
        """Create a gateway backed by a FakeHttpClient and mocked adapters."""
        client = FakeHttpClient()
        conn = DhanConnection(client=client)

        # Replace each adapter with a MagicMock so we can assert calls
        conn._market_data = MagicMock()
        conn._orders = MagicMock()
        conn._portfolio = MagicMock()

        gateway = DhanWireAdapter(conn)
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
        """gateway.funds() must call portfolio.get_balance."""
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

        from domain import OrderResponse

        expected = OrderResponse(
            success=True,
            order_id="ORD-001",
            broker_order_id="ORD-001",
            message="Order placed",
        )
        conn._orders.place_order.return_value = expected

        result = gateway.place_order(_order_request(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=10,
        ))

        call_args = conn._orders.place_order.call_args[0]
        assert len(call_args) == 1
        request = call_args[0]
        assert isinstance(request, OrderRequest)
        assert request.symbol == "RELIANCE"
        assert request.exchange == "NSE"
        assert request.transaction_type.value == "BUY"
        assert request.quantity == 10
        assert request.price is None or request.price == Decimal("0")
        assert request.order_type.value == "MARKET"
        assert request.trigger_price is None
        assert request.product_type.value == "INTRADAY"
        assert request.validity.value == "DAY"
        assert request.correlation_id is None
        assert isinstance(result, OrderResponse)
        assert result.success is True
        assert result.order_id == "ORD-001"

    def test_place_order_mcx_resolves_canonical_segment(self):
        """MCX exchange must map to ExchangeSegment.MCX, not silently fall back to NSE."""
        from domain import ExchangeSegment, OrderResponse

        gateway, conn = self._make_gateway()
        conn._orders.place_order.return_value = OrderResponse.ok(
            order_id="ORD-MCX", message="Order placed"
        )

        gateway.place_order(_order_request(symbol="GOLD", exchange="MCX", side="BUY", quantity=1))

        request = conn._orders.place_order.call_args[0][0]
        assert request.exchange_segment is ExchangeSegment.MCX

    def test_place_order_unknown_exchange_raises(self):
        gateway, _conn = self._make_gateway()
        import pytest

        with pytest.raises(ValueError, match="Unknown exchange"):
            gateway.place_order(_order_request(symbol="X", exchange="BOGUS", quantity=1))

    # -- lifecycle -------------------------------------------------------

    def test_close_closes_client(self):
        """gateway.close() must propagate to the underlying HTTP client."""
        client = FakeHttpClient()
        conn = DhanConnection(client=client)
        # Replace the client's close with a mock to track the call
        client.close = MagicMock()
        gateway = DhanWireAdapter(conn)

        gateway.close()

        client.close.assert_called_once()

    # -- connection liveness (unified contract) --------------------------

    def test_is_connected_true_when_rest_auth_only(self):
        """A REST-only session (no WS feed) with a usable token is connected.

        Regression: previously ``is_connected`` fell back to ``False`` when no
        market feed existed, making a healthy REST session look disconnected.
        """
        client = FakeHttpClient(access_token="valid-token")
        conn = DhanConnection(client=client)
        gateway = DhanWireAdapter(conn)
        assert gateway.is_connected is True

    def test_is_connected_false_when_token_missing(self):
        """Without a usable access token the session is not connected."""
        client = FakeHttpClient(access_token="")
        conn = DhanConnection(client=client)
        gateway = DhanWireAdapter(conn)
        assert gateway.is_connected is False

    def test_is_connected_true_when_feed_down_but_rest_auth_ok(self):
        """REST auth remains sufficient when a WS feed exists but is disconnected."""
        client = FakeHttpClient(access_token="valid-token")
        conn = DhanConnection(client=client)
        feed = MagicMock()
        feed.is_connected = False
        conn.market_feed = feed
        gateway = DhanWireAdapter(conn)
        assert gateway.is_connected is True

    # -- history batch (shared batch_execute) ---------------------------

    def test_history_batch_concatenates_per_symbol_frames(self):
        """history_batch routes through the shared helper and concatenates."""
        import pandas as pd

        gateway, conn = self._make_gateway()
        conn._historical = MagicMock()

        def _fake_hist(symbol, exchange, from_str, to_str, tf):
            return pd.DataFrame({"symbol": [symbol], "close": [1.0]})

        conn._historical.get_historical.side_effect = _fake_hist

        result = gateway.history_batch(["RELIANCE", "TCS"], "NSE")
        assert set(result["symbol"]) == {"RELIANCE", "TCS"}
        assert len(result) == 2

    # -- depth-200 constraint discoverability (#5) ----------------------

    def test_describe_exposes_depth_200_limit(self):
        from brokers.providers.dhan.config.capabilities import (
            DHAN_DEPTH_200_MAX_INSTRUMENTS_PER_CONNECTION,
        )

        client = FakeHttpClient()
        conn = DhanConnection(client=client)
        gateway = DhanWireAdapter(conn)
        assert (
            gateway.describe()["depth_200_max_instruments_per_connection"]
            == DHAN_DEPTH_200_MAX_INSTRUMENTS_PER_CONNECTION
            == 1
        )


