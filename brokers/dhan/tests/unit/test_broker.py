"""TDD tests for DhanBroker — DhanHQ broker adapter.

Tests use monkeypatching to avoid real API calls.
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from brokers.common.core.connection import Capability
from brokers.common.core.enums import (
    ExchangeSegment,
    OrderType,
    ProductType,
    TransactionType,
)
from brokers.common.core.models import OrderRequest
from brokers.dhan import DhanBroker


class TestDhanBrokerInit:
    def test_requires_credentials(self):
        with pytest.raises(ValueError):
            DhanBroker(client_id="", access_token="")

    def test_minimal_init(self):
        broker = DhanBroker(client_id="test123", access_token="tok_abc")
        assert broker.client_id == "test123"
        assert broker.name == "dhan"
        assert broker.broker_id == "test123"

    def test_capabilities(self, monkeypatch):
        broker = DhanBroker(client_id="test", access_token="tok")
        assert broker.has_capability(Capability.MARKET_DATA)
        assert broker.has_capability(Capability.ORDER_COMMAND)
        assert broker.has_capability(Capability.PORTFOLIO)
        assert broker.has_capability(Capability.OPTIONS_CHAIN)

    def test_rate_limiter_configured(self, monkeypatch):
        broker = DhanBroker(client_id="test", access_token="tok")
        limiter = broker.rate_limiter
        assert "orders" in limiter.categories()
        assert "quotes" in limiter.categories()
        assert "data" in limiter.categories()

    def test_retry_executor_configured(self, monkeypatch):
        broker = DhanBroker(client_id="test", access_token="tok")
        assert broker.executor is not None


class TestDhanBrokerConnection:
    def test_connect_with_valid_credentials(self, monkeypatch):
        mock_dhan = MagicMock()
        monkeypatch.setattr("brokers.dhan.dhanhq", lambda ctx: mock_dhan)

        broker = DhanBroker(client_id="test", access_token="tok")
        result = broker.connect()
        assert result is True
        assert broker.is_connected()

    def test_disconnect(self, monkeypatch):
        broker = DhanBroker(client_id="test", access_token="tok")
        broker.connect()
        result = broker.disconnect()
        assert result is True

    def test_reconnect(self, monkeypatch):
        broker = DhanBroker(client_id="test", access_token="tok")
        result = broker.reconnect()
        assert result is True


class TestDhanBrokerPlaceOrder:
    def test_place_order_calls_sdk(self, monkeypatch):
        mock_dhan = MagicMock()
        mock_dhan.place_order.return_value = {
            "status": "success",
            "data": {"orderId": "DHAN12345"},
        }
        monkeypatch.setattr("brokers.dhan.dhanhq", lambda ctx: mock_dhan)

        broker = DhanBroker(client_id="test", access_token="tok")
        broker.connect()

        req = OrderRequest(
            security_id="2885",
            exchange_segment=ExchangeSegment.NSE,
            transaction_type=TransactionType.BUY,
            quantity=10,
            price=Decimal("2500"),
            order_type=OrderType.LIMIT,
            product_type=ProductType.CNC,
        )
        resp = broker.place_order(req)
        assert resp.success is True
        assert resp.order_id == "DHAN12345"
        mock_dhan.place_order.assert_called_once()

    def test_place_order_failure(self, monkeypatch):
        mock_dhan = MagicMock()
        mock_dhan.place_order.return_value = {
            "status": "failure",
            "remarks": "Insufficient margin",
        }
        monkeypatch.setattr("brokers.dhan.dhanhq", lambda ctx: mock_dhan)

        broker = DhanBroker(client_id="test", access_token="tok")
        broker.connect()

        resp = broker.place_order(
            OrderRequest(
                security_id="2885",
                exchange_segment=ExchangeSegment.NSE,
                transaction_type=TransactionType.BUY,
                quantity=10,
                order_type=OrderType.MARKET,
            )
        )
        assert resp.success is False
        assert "Insufficient" in resp.message

    def test_place_order_disconnected(self, monkeypatch):
        broker = DhanBroker(client_id="test", access_token="tok")
        resp = broker.place_order(
            OrderRequest(
                security_id="2885",
                exchange_segment=ExchangeSegment.NSE,
                transaction_type=TransactionType.BUY,
                quantity=10,
                order_type=OrderType.MARKET,
            )
        )
        assert resp.success is False


class TestDhanBrokerQuote:
    def test_get_quote(self, monkeypatch):
        mock_dhan = MagicMock()
        mock_dhan.quote_data.return_value = {
            "status": "success",
            "data": {"last_price": 2500.50, "volume": 100000},
        }
        monkeypatch.setattr("brokers.dhan.dhanhq", lambda ctx: mock_dhan)

        broker = DhanBroker(client_id="test", access_token="tok")
        broker.connect()

        quote = broker.get_quote("2885", ExchangeSegment.NSE)
        assert quote is not None
        assert quote.last_price == Decimal("2500.50")

    def test_get_quote_failure(self, monkeypatch):
        mock_dhan = MagicMock()
        mock_dhan.quote_data.return_value = {
            "status": "failure",
            "remarks": "Rate limit exceeded",
        }
        monkeypatch.setattr("brokers.dhan.dhanhq", lambda ctx: mock_dhan)

        broker = DhanBroker(client_id="test", access_token="tok")
        broker.connect()

        quote = broker.get_quote("2885", ExchangeSegment.NSE)
        assert quote is None


class TestDhanBrokerPortfolio:
    def test_get_positions(self, monkeypatch):
        mock_dhan = MagicMock()
        mock_dhan.get_positions.return_value = {
            "status": "success",
            "data": [
                {
                    "securityId": "2885",
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "netQuantity": 100,
                    "buyAveragePrice": 2480.0,
                    "lastPrice": 2500.0,
                    "productType": "INTRADAY",
                }
            ],
        }
        monkeypatch.setattr("brokers.dhan.dhanhq", lambda ctx: mock_dhan)

        broker = DhanBroker(client_id="test", access_token="tok")
        broker.connect()

        positions = broker.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "RELIANCE"
        assert positions[0].exchange == "NSE"
        assert positions[0].quantity == 100

    def test_get_holdings(self, monkeypatch):
        mock_dhan = MagicMock()
        mock_dhan.get_holdings.return_value = {
            "status": "success",
            "data": [
                {
                    "securityId": "2885",
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "quantity": 50,
                    "availableQuantity": 50,
                    "costPrice": 2450.0,
                    "lastPrice": 2500.0,
                    "pnlValue": 2500.0,
                }
            ],
        }
        monkeypatch.setattr("brokers.dhan.dhanhq", lambda ctx: mock_dhan)

        broker = DhanBroker(client_id="test", access_token="tok")
        broker.connect()

        holdings = broker.get_holdings()
        assert len(holdings) == 1
        assert holdings[0].symbol == "RELIANCE"
        assert holdings[0].quantity == 50

    def test_get_fund_limits(self, monkeypatch):
        mock_dhan = MagicMock()
        mock_dhan.get_fund_limits.return_value = {
            "status": "success",
            "data": {"availableBalance": 500000},
        }
        monkeypatch.setattr("brokers.dhan.dhanhq", lambda ctx: mock_dhan)

        broker = DhanBroker(client_id="test", access_token="tok")
        broker.connect()

        funds = broker.get_fund_limits()
        assert funds.available_balance == Decimal("500000")


class TestDhanBrokerOrderStream:
    def test_broker_order_stream_subscribe(self):
        broker = DhanBroker(client_id="test", access_token="tok")
        broker.connect()

        # Mock the order_stream provider
        mock_order_stream = MagicMock()
        mock_order_stream.subscribe_order_stream.return_value = True
        broker.order_stream = mock_order_stream

        result = broker.subscribe_order_stream(["DHAN12345", "DHAN67890"])
        assert result is True
        mock_order_stream.subscribe_order_stream.assert_called_once_with(["DHAN12345", "DHAN67890"])

    def test_broker_order_stream_unsubscribe(self):
        broker = DhanBroker(client_id="test", access_token="tok")
        broker.connect()

        # Mock the order_stream provider
        mock_order_stream = MagicMock()
        mock_order_stream.unsubscribe_order_stream.return_value = True
        broker.order_stream = mock_order_stream

        result = broker.unsubscribe_order_stream(["DHAN12345", "DHAN67890"])
        assert result is True
        mock_order_stream.unsubscribe_order_stream.assert_called_once_with(
            ["DHAN12345", "DHAN67890"]
        )

    def test_broker_order_stream_status(self):
        broker = DhanBroker(client_id="test", access_token="tok")
        broker.connect()

        # Mock the order_stream provider
        mock_order_stream = MagicMock()
        mock_order_stream.get_order_stream_status.return_value = {
            "connected": True,
            "subscriptions": 1,
            "listeners": 0,
        }
        broker.order_stream = mock_order_stream

        status = broker.get_order_stream_status()
        assert status["connected"] is True
        assert status["subscriptions"] == 1
        assert status["listeners"] == 0
        mock_order_stream.get_order_stream_status.assert_called_once()

    def test_broker_order_stream_add_listener(self):
        broker = DhanBroker(client_id="test", access_token="tok")
        broker.connect()

        # Mock the order_stream provider
        mock_order_stream = MagicMock()
        mock_order_stream.add_order_listener.return_value = None
        broker.order_stream = mock_order_stream

        mock_listener = MagicMock()
        broker.add_order_listener(mock_listener)
        mock_order_stream.add_order_listener.assert_called_once_with(mock_listener)

    def test_broker_order_stream_remove_listener(self):
        broker = DhanBroker(client_id="test", access_token="tok")
        broker.connect()

        # Mock the order_stream provider
        mock_order_stream = MagicMock()
        mock_order_stream.remove_order_listener.return_value = None
        broker.order_stream = mock_order_stream

        mock_listener = MagicMock()
        broker.remove_order_listener(mock_listener)
        mock_order_stream.remove_order_listener.assert_called_once_with(mock_listener)


class TestDhanBrokerIdempotency:
    def test_idempotency_caching(self, monkeypatch):
        mock_dhan = MagicMock()
        mock_dhan.place_order.return_value = {
            "status": "success",
            "data": {"orderId": "DHAN_IDEMP_1"},
        }
        monkeypatch.setattr("brokers.dhan.dhanhq", lambda ctx: mock_dhan)

        broker = DhanBroker(client_id="test", access_token="tok")
        broker.connect()

        req1 = OrderRequest(
            security_id="2885",
            exchange_segment=ExchangeSegment.NSE,
            transaction_type=TransactionType.BUY,
            quantity=10,
            price=Decimal("2500"),
            order_type=OrderType.LIMIT,
            product_type=ProductType.CNC,
            correlation_id="corr_key_123",
        )

        # First placement
        resp1 = broker.place_order(req1)
        assert resp1.success is True
        assert resp1.order_id == "DHAN_IDEMP_1"
        assert mock_dhan.place_order.call_count == 1

        # Second placement with same correlation ID
        resp2 = broker.place_order(req1)
        assert resp2.success is True
        assert resp2.order_id == "DHAN_IDEMP_1"
        # Call count should still be 1 (retrieved from cache)
        assert mock_dhan.place_order.call_count == 1
