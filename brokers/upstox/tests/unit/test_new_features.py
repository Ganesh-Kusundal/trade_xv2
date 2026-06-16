"""Tests for Upstox newly wired adapters: IPO, Payments, Mutual Funds, Fundamentals."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_http_client():
    client = MagicMock()
    return client


@pytest.fixture
def mock_url_resolver():
    resolver = MagicMock()
    resolver.ipo_url.return_value = "https://api.upstox.com/v2/ipo"
    resolver.payments_url.return_value = "https://api.upstox.com/v2/payments"
    resolver.mutual_funds_url.return_value = "https://api.upstox.com/v2/mutual-funds"
    resolver.fundamentals_url.return_value = "https://api.upstox.com/v2/fundamentals"
    return resolver


# IPO Tests

class TestUpstoxIpoAdapter:
    def test_get_ipos_returns_list(self, mock_http_client, mock_url_resolver):
        from brokers.upstox.ipo.client import UpstoxIpoClient
        from brokers.upstox.ipo.adapter import UpstoxIpoAdapter

        mock_http_client.get_json.return_value = {
            "status": "success",
            "data": [
                {"name": "IPO1", "status": "open"},
                {"name": "IPO2", "status": "open"},
            ]
        }

        client = UpstoxIpoClient(mock_http_client, mock_url_resolver)
        adapter = UpstoxIpoAdapter(client)
        result = adapter.get_ipos(status="open")

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["name"] == "IPO1"
        mock_http_client.get_json.assert_called_once()

    def test_get_ipos_empty_response(self, mock_http_client, mock_url_resolver):
        from brokers.upstox.ipo.client import UpstoxIpoClient
        from brokers.upstox.ipo.adapter import UpstoxIpoAdapter

        mock_http_client.get_json.return_value = {"status": "success", "data": []}

        client = UpstoxIpoClient(mock_http_client, mock_url_resolver)
        adapter = UpstoxIpoAdapter(client)
        result = adapter.get_ipos()

        assert isinstance(result, list)
        assert len(result) == 0


# Payments Tests

class TestUpstoxPaymentsAdapter:
    def test_initiate_payout(self, mock_http_client, mock_url_resolver):
        from brokers.upstox.payments.client import UpstoxPaymentsClient
        from brokers.upstox.payments.adapter import UpstoxPaymentsAdapter

        mock_http_client.post_json.return_value = {
            "status": "success",
            "data": {"payout_id": "PAY123"}
        }

        client = UpstoxPaymentsClient(mock_http_client, mock_url_resolver)
        adapter = UpstoxPaymentsAdapter(client)
        result = adapter.initiate_payout({"amount": 1000})

        assert result["status"] == "success"
        assert result["data"]["payout_id"] == "PAY123"

    def test_get_payouts(self, mock_http_client, mock_url_resolver):
        from brokers.upstox.payments.client import UpstoxPaymentsClient
        from brokers.upstox.payments.adapter import UpstoxPaymentsAdapter

        mock_http_client.get_json.return_value = {
            "status": "success",
            "data": [{"payout_id": "PAY123", "amount": 1000}]
        }

        client = UpstoxPaymentsClient(mock_http_client, mock_url_resolver)
        adapter = UpstoxPaymentsAdapter(client)
        result = adapter.get_payouts()

        assert isinstance(result, list)
        assert len(result) == 1

    def test_cancel_payout(self, mock_http_client, mock_url_resolver):
        from brokers.upstox.payments.client import UpstoxPaymentsClient
        from brokers.upstox.payments.adapter import UpstoxPaymentsAdapter

        mock_http_client.delete_json.return_value = {"status": "success"}

        client = UpstoxPaymentsClient(mock_http_client, mock_url_resolver)
        adapter = UpstoxPaymentsAdapter(client)
        result = adapter.cancel_payout("PAY123")

        assert result["status"] == "success"


# Mutual Funds Tests

class TestUpstoxMutualFundsAdapter:
    def test_get_holdings(self, mock_http_client, mock_url_resolver):
        from brokers.upstox.mutual_funds.client import UpstoxMutualFundsClient
        from brokers.upstox.mutual_funds.adapter import UpstoxMutualFundsAdapter

        mock_http_client.get_json.return_value = {
            "status": "success",
            "data": [
                {"fund_name": "HDFC Equity Fund", "units": 100.5},
            ]
        }

        client = UpstoxMutualFundsClient(mock_http_client, mock_url_resolver)
        adapter = UpstoxMutualFundsAdapter(client)
        result = adapter.get_holdings()

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["fund_name"] == "HDFC Equity Fund"

    def test_place_order(self, mock_http_client, mock_url_resolver):
        from brokers.upstox.mutual_funds.client import UpstoxMutualFundsClient
        from brokers.upstox.mutual_funds.adapter import UpstoxMutualFundsAdapter

        mock_http_client.post_json.return_value = {
            "status": "success",
            "data": {"order_id": "MF123"}
        }

        client = UpstoxMutualFundsClient(mock_http_client, mock_url_resolver)
        adapter = UpstoxMutualFundsAdapter(client)
        result = adapter.place_order({"fund_name": "HDFC Equity Fund", "amount": 5000})

        assert result["status"] == "success"
        assert result["data"]["order_id"] == "MF123"


# Fundamentals Tests

class TestUpstoxFundamentalsAdapter:
    def test_get_pnl(self, mock_http_client, mock_url_resolver):
        from brokers.upstox.fundamentals.client import UpstoxFundamentalsClient
        from brokers.upstox.fundamentals.adapter import UpstoxFundamentalsAdapter

        mock_http_client.get_json.return_value = {
            "status": "success",
            "data": {
                "isin": "INE002A01018",
                "revenue": 100000,
                "profit": 25000,
            }
        }

        client = UpstoxFundamentalsClient(mock_http_client, mock_url_resolver)
        adapter = UpstoxFundamentalsAdapter(client)
        result = adapter.get_pnl("INE002A01018")

        assert result["status"] == "success"
        assert result["data"]["isin"] == "INE002A01018"

    def test_get_ratios(self, mock_http_client, mock_url_resolver):
        from brokers.upstox.fundamentals.client import UpstoxFundamentalsClient
        from brokers.upstox.fundamentals.adapter import UpstoxFundamentalsAdapter

        mock_http_client.get_json.return_value = {
            "status": "success",
            "data": {
                "pe_ratio": 25.5,
                "pb_ratio": 3.2,
            }
        }

        client = UpstoxFundamentalsClient(mock_http_client, mock_url_resolver)
        adapter = UpstoxFundamentalsAdapter(client)
        result = adapter.get_ratios("INE002A01018")

        assert result["status"] == "success"
        assert result["data"]["pe_ratio"] == 25.5


# Gateway Integration Tests

class TestUpstoxGatewayNewFeatures:
    def test_gateway_ipo_property(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway
        from brokers.upstox.broker import UpstoxBroker
        from unittest.mock import MagicMock

        mock_broker = MagicMock(spec=UpstoxBroker)
        mock_broker.ipo = MagicMock()

        gateway = UpstoxBrokerGateway(mock_broker)
        assert gateway.ipo is not None

    def test_gateway_payments_property(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway
        from brokers.upstox.broker import UpstoxBroker
        from unittest.mock import MagicMock

        mock_broker = MagicMock(spec=UpstoxBroker)
        mock_broker.payments = MagicMock()

        gateway = UpstoxBrokerGateway(mock_broker)
        assert gateway.payments is not None

    def test_gateway_mutual_funds_property(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway
        from brokers.upstox.broker import UpstoxBroker
        from unittest.mock import MagicMock

        mock_broker = MagicMock(spec=UpstoxBroker)
        mock_broker.mutual_funds = MagicMock()

        gateway = UpstoxBrokerGateway(mock_broker)
        assert gateway.mutual_funds is not None

    def test_gateway_fundamentals_property(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway
        from brokers.upstox.broker import UpstoxBroker
        from unittest.mock import MagicMock

        mock_broker = MagicMock(spec=UpstoxBroker)
        mock_broker.fundamentals = MagicMock()

        gateway = UpstoxBrokerGateway(mock_broker)
        assert gateway.fundamentals is not None

    def test_gateway_capabilities_includes_new_features(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway
        from brokers.upstox.broker import UpstoxBroker
        from unittest.mock import MagicMock

        mock_broker = MagicMock(spec=UpstoxBroker)
        mock_broker.portfolio = MagicMock()
        mock_broker.portfolio.get_fund_limits.return_value = MagicMock()
        mock_broker.portfolio.get_positions.return_value = []
        mock_broker.portfolio.get_holdings.return_value = []

        gateway = UpstoxBrokerGateway(mock_broker)
        caps = gateway.capabilities()

        assert caps.ipo is True
        assert caps.mutual_funds is True
        assert caps.fundamentals is True
        assert caps.payments is True
        assert caps.user_profile is True
        assert caps.convert_position is True
