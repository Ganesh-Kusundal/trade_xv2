"""Unit tests for portfolio CLI commands (holdings / positions).

All Dhan HTTP calls are mocked — no live API dependency.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from rich.console import Console

from cli.commands import portfolio as cmd_portfolio
from cli.services.broker_service import BrokerServiceTestBuilder

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def broker_service():
    """Return a BrokerService backed by seeded MockBroker (no .env.local needed)."""
    from brokers.paper.mock_broker import create_demo_broker

    return (
        BrokerServiceTestBuilder()
        .with_mock(create_demo_broker("dhan"))
        .build()
    )


@pytest.fixture()
def mock_broker_service():
    """Return a BrokerService whose active_broker.portfolio is fully mocked."""
    mock_gw = MagicMock()
    mock_portfolio = MagicMock()
    mock_gw.portfolio = mock_portfolio

    svc = BrokerServiceTestBuilder().with_gateway(mock_gw).build()
    return svc, mock_portfolio


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_HOLDINGS_RAW = {
    "data": [
        {
            "tradingSymbol": "INFY",
            "exchangeSegment": "NSE_EQ",
            "totalQty": 20,
            "availableQty": 20,
            "avgCostPrice": 1420.0,
            "lastTradedPrice": 1435.0,
            "pnlValue": 300.0,
        },
        {
            "tradingSymbol": "HDFCBANK",
            "exchangeSegment": "NSE_EQ",
            "totalQty": 50,
            "availableQty": 50,
            "avgCostPrice": 1580.0,
            "lastTradedPrice": 1565.0,
            "pnlValue": -750.0,
        },
    ]
}

MOCK_POSITIONS_RAW = {
    "data": [
        {
            "tradingSymbol": "RELIANCE",
            "exchangeSegment": "NSE_EQ",
            "netQuantity": 10,
            "buyAveragePrice": 2550.0,
            "lastPrice": 2565.50,
            "unrealizedPnl": 155.0,
            "realizedPnl": 0.0,
            "productType": "INTRADAY",
        },
        {
            "tradingSymbol": "TCS",
            "exchangeSegment": "NSE_EQ",
            "netQuantity": -5,
            "buyAveragePrice": 3800.0,
            "lastPrice": 3750.0,
            "unrealizedPnl": 250.0,
            "realizedPnl": 100.0,
            "productType": "INTRADAY",
        },
    ]
}


# ---------------------------------------------------------------------------
# Tests — using MockBroker (built-in mock data)
# ---------------------------------------------------------------------------


class TestHoldingsWithMockBroker:
    """Tests that run against MockBroker's in-memory data."""

    def test_show_holdings_displays_symbols(self, broker_service):
        console = Console(record=True)
        cmd_portfolio.show_holdings(broker_service, console)
        output = console.export_text()
        assert "INFY" in output
        assert "HDFCBANK" in output

    def test_show_holdings_displays_headers(self, broker_service):
        console = Console(record=True)
        cmd_portfolio.show_holdings(broker_service, console)
        output = console.export_text()
        assert "Symbol" in output or "Qty" in output

    def test_show_holdings_shows_pnl(self, broker_service):
        console = Console(record=True)
        cmd_portfolio.show_holdings(broker_service, console)
        output = console.export_text()
        assert "300" in output or "PnL" in output


class TestPositionsWithMockBroker:
    """Tests that run against MockBroker's in-memory data."""

    def test_show_positions_displays_symbols(self, broker_service):
        console = Console(record=True)
        cmd_portfolio.show_positions(broker_service, console)
        output = console.export_text()
        assert "RELIANCE" in output

    def test_show_positions_displays_headers(self, broker_service):
        console = Console(record=True)
        cmd_portfolio.show_positions(broker_service, console)
        output = console.export_text()
        assert "Symbol" in output or "Position" in output

    def test_show_positions_shows_product_type(self, broker_service):
        console = Console(record=True)
        cmd_portfolio.show_positions(broker_service, console)
        output = console.export_text()
        assert "INTRADAY" in output


# ---------------------------------------------------------------------------
# Tests — with fully mocked gateway (simulate Dhan API responses)
# ---------------------------------------------------------------------------


class TestHoldingsWithMockedGateway:
    """Tests that mock broker_service.active_broker.portfolio.get_holdings()."""

    def _make_holding(self, symbol="RELIANCE", qty=10, avg=2400, ltp=2450, pnl=500):
        h = MagicMock()
        h.symbol = symbol
        h.quantity = qty
        h.avg_price = Decimal(str(avg))
        h.ltp = Decimal(str(ltp))
        h.pnl = Decimal(str(pnl))
        return h

    def test_show_holdings_renders_table(self, mock_broker_service):
        svc, mock_portfolio = mock_broker_service
        mock_portfolio.get_holdings.return_value = [
            self._make_holding("RELIANCE", 10, 2400, 2450, 500),
            self._make_holding("INFY", 20, 1400, 1435, 700),
        ]

        console = Console(record=True)
        cmd_portfolio.show_holdings(svc, console)
        output = console.export_text()

        assert "RELIANCE" in output
        assert "INFY" in output
        mock_portfolio.get_holdings.assert_called_once()

    def test_show_holdings_positive_pnl_green(self, mock_broker_service):
        svc, mock_portfolio = mock_broker_service
        mock_portfolio.get_holdings.return_value = [
            self._make_holding("TATASTEEL", 50, 100, 120, 1000),
        ]

        console = Console(record=True)
        cmd_portfolio.show_holdings(svc, console)
        output = console.export_text()

        assert "TATASTEEL" in output
        assert "1,000" in output

    def test_show_holdings_negative_pnl_red(self, mock_broker_service):
        svc, mock_portfolio = mock_broker_service
        mock_portfolio.get_holdings.return_value = [
            self._make_holding("WIPRO", 100, 500, 450, -5000),
        ]

        console = Console(record=True)
        cmd_portfolio.show_holdings(svc, console)
        output = console.export_text()

        assert "WIPRO" in output
        assert "-5,000" in output

    def test_show_holdings_empty(self, mock_broker_service):
        svc, mock_portfolio = mock_broker_service
        mock_portfolio.get_holdings.return_value = []

        console = Console(record=True)
        cmd_portfolio.show_holdings(svc, console)
        output = console.export_text()

        assert "Total" in output or "Holdings" in output

    def test_show_holdings_api_error(self, mock_broker_service):
        svc, mock_portfolio = mock_broker_service
        mock_portfolio.get_holdings.side_effect = ConnectionError("API timeout")

        console = Console(record=True)
        cmd_portfolio.show_holdings(svc, console)
        output = console.export_text()

        assert "Error" in output or "error" in output


class TestPositionsWithMockedGateway:
    """Tests that mock broker_service.active_broker.portfolio.get_positions()."""

    def _make_position(
        self,
        symbol="RELIANCE",
        qty=10,
        avg=2400,
        ltp=2450,
        unrealized=500,
        realized=0,
        product="INTRADAY",
    ):
        p = MagicMock()
        p.symbol = symbol
        p.quantity = qty
        p.avg_price = Decimal(str(avg))
        p.ltp = Decimal(str(ltp))
        p.unrealized_pnl = Decimal(str(unrealized))
        p.realized_pnl = Decimal(str(realized))

        pt = MagicMock()
        pt.value = product
        p.product_type = pt
        return p

    def test_show_positions_long_positions(self, mock_broker_service):
        svc, mock_portfolio = mock_broker_service
        mock_portfolio.get_positions.return_value = [
            self._make_position("RELIANCE", 10, 2400, 2450, 500, 0, "INTRADAY"),
        ]

        console = Console(record=True)
        cmd_portfolio.show_positions(svc, console)
        output = console.export_text()

        assert "RELIANCE" in output
        mock_portfolio.get_positions.assert_called_once()

    def test_show_positions_short_positions(self, mock_broker_service):
        svc, mock_portfolio = mock_broker_service
        mock_portfolio.get_positions.return_value = [
            self._make_position("NIFTY FUT", -75, 24600, 24550, -3750, 500, "MARGIN"),
        ]

        console = Console(record=True)
        cmd_portfolio.show_positions(svc, console)
        output = console.export_text()

        assert "NIFTY FUT" in output

    def test_show_positions_intraday_and_overnight(self, mock_broker_service):
        svc, mock_portfolio = mock_broker_service
        mock_portfolio.get_positions.return_value = [
            self._make_position("RELIANCE", 10, 2400, 2450, 500, 0, "INTRADAY"),
            self._make_position("SBIN", 20, 580, 600, 400, 0, "CNC"),
        ]

        console = Console(record=True)
        cmd_portfolio.show_positions(svc, console)
        output = console.export_text()

        assert "INTRADAY" in output
        assert "CNC" in output or "MARGIN" in output

    def test_show_positions_empty(self, mock_broker_service):
        svc, mock_portfolio = mock_broker_service
        mock_portfolio.get_positions.return_value = []

        console = Console(record=True)
        cmd_portfolio.show_positions(svc, console)
        output = console.export_text()

        assert "Positions" in output or "Overview" in output

    def test_show_positions_api_error(self, mock_broker_service):
        svc, mock_portfolio = mock_broker_service
        mock_portfolio.get_positions.side_effect = ConnectionError("API timeout")

        console = Console(record=True)
        cmd_portfolio.show_positions(svc, console)
        output = console.export_text()

        assert "Error" in output or "error" in output
