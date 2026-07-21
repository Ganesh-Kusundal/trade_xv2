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
        from brokers.providers.upstox.ipo.adapter import UpstoxIpoAdapter
        from brokers.providers.upstox.ipo.client import UpstoxIpoClient

        mock_http_client.get_json.return_value = {
            "status": "success",
            "data": [
                {"name": "IPO1", "status": "open"},
                {"name": "IPO2", "status": "open"},
            ],
        }

        client = UpstoxIpoClient(mock_http_client, mock_url_resolver)
        adapter = UpstoxIpoAdapter(client)
        result = adapter.get_ipos(status="open")

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["name"] == "IPO1"
        mock_http_client.get_json.assert_called_once()

    def test_get_ipos_empty_response(self, mock_http_client, mock_url_resolver):
        from brokers.providers.upstox.ipo.adapter import UpstoxIpoAdapter
        from brokers.providers.upstox.ipo.client import UpstoxIpoClient

        mock_http_client.get_json.return_value = {"status": "success", "data": []}

        client = UpstoxIpoClient(mock_http_client, mock_url_resolver)
        adapter = UpstoxIpoAdapter(client)
        result = adapter.get_ipos()

        assert isinstance(result, list)
        assert len(result) == 0


# Gateway Integration Tests


class TestUpstoxGatewayNewFeatures:
    def _make_mock_broker(self):
        from unittest.mock import MagicMock

        from brokers.providers.upstox.broker import UpstoxBroker

        mock_broker = MagicMock(spec=UpstoxBroker)
        mock_broker.instrument_resolver = MagicMock()
        mock_broker.order_command = MagicMock()
        mock_broker.market_data_v2 = MagicMock()
        mock_broker.market_data_v3 = MagicMock()
        mock_broker.historical_v2 = MagicMock()
        return mock_broker

    def test_gateway_ipo_property(self):
        from brokers.providers.upstox.wire import UpstoxWireAdapter

        mock_broker = self._make_mock_broker()
        mock_broker.ipo = MagicMock()

        gateway = UpstoxWireAdapter(mock_broker)
        assert gateway.extended is not None
        assert hasattr(gateway.extended, "get_ipos")

    def test_gateway_payments_property(self):
        from brokers.providers.upstox.wire import UpstoxWireAdapter

        mock_broker = self._make_mock_broker()
        mock_broker.payments = MagicMock()

        gateway = UpstoxWireAdapter(mock_broker)
        assert gateway.extended is not None
        assert hasattr(gateway.extended, "initiate_payout")

    def test_gateway_mutual_funds_property(self):
        from brokers.providers.upstox.wire import UpstoxWireAdapter

        mock_broker = self._make_mock_broker()
        mock_broker.mutual_funds = MagicMock()

        gateway = UpstoxWireAdapter(mock_broker)
        assert gateway.extended is not None
        assert hasattr(gateway.extended, "get_mutual_fund_holdings")

    def test_gateway_fundamentals_property(self):
        from brokers.providers.upstox.wire import UpstoxWireAdapter

        mock_broker = self._make_mock_broker()
        mock_broker.fundamentals = MagicMock()

        gateway = UpstoxWireAdapter(mock_broker)
        assert gateway.extended is not None
        assert hasattr(gateway.extended, "get_pnl")

    def test_gateway_capabilities_includes_new_features(self):
        from brokers.providers.upstox.wire import UpstoxWireAdapter

        mock_broker = self._make_mock_broker()
        mock_broker.portfolio = MagicMock()
        mock_broker.portfolio.get_fund_limits.return_value = MagicMock()
        mock_broker.portfolio.get_positions.return_value = []
        mock_broker.portfolio.get_holdings.return_value = []
        mock_broker.instrument_resolver = MagicMock()
        mock_broker.order_command = MagicMock()  # Required by gateway __init__

        gateway = UpstoxWireAdapter(mock_broker)
        caps = gateway.capabilities()

        assert caps.supports_news is True
        assert caps.supports_fundamentals is True
        assert caps.supports_forever_order is True
        assert caps.supports_portfolio_stream is True
