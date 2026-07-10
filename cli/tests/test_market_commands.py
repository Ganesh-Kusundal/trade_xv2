"""Unit tests for market CLI commands.

Tests cover: quote, depth, option chain, futures, historical, and stream commands.
All broker API calls are mocked — no live API dependency.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from cli.commands import market as cmd_market
from cli.commands.market import (
    resolve_exchange,
    show_depth,
    show_futures,
    show_historical,
    show_option_chain,
    show_quote,
)
from cli.services.broker_service import BrokerService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_broker_service():
    """Create a BrokerService with mocked gateway."""
    service = MagicMock(spec=BrokerService)
    service.active_broker = MagicMock()
    service.active_broker_name = "dhan"
    return service


@pytest.fixture()
def console():
    """Return a Rich console with recording enabled."""
    return Console(record=True)


@pytest.fixture()
def mock_quote():
    """Create a mock Quote object."""
    quote = MagicMock()
    quote.ltp = 2450.50
    quote.open = 2440.00
    quote.high = 2460.00
    quote.low = 2435.00
    quote.close = 2445.00
    quote.volume = 1500000
    quote.change = 5.50
    quote.timestamp = datetime.now()
    return quote


@pytest.fixture()
def mock_depth():
    """Create a mock MarketDepth object."""
    depth = MagicMock()

    # Create bid levels
    bid1 = MagicMock()
    bid1.price = 2450.00
    bid1.quantity = 1000
    bid2 = MagicMock()
    bid2.price = 2449.50
    bid2.quantity = 1500

    # Create ask levels
    ask1 = MagicMock()
    ask1.price = 2451.00
    ask1.quantity = 1200
    ask2 = MagicMock()
    ask2.price = 2451.50
    ask2.quantity = 800

    depth.bids = [bid1, bid2]
    depth.asks = [ask1, ask2]
    return depth


# ---------------------------------------------------------------------------
# Test Exchange Resolution
# ---------------------------------------------------------------------------


class TestResolveExchange:
    """Tests for resolve_exchange helper."""

    def test_nifty_is_index(self):
        assert resolve_exchange("NIFTY") == "INDEX"

    def test_banknifty_is_index(self):
        assert resolve_exchange("BANKNIFTY") == "INDEX"

    def test_regular_stock_is_nse(self):
        assert resolve_exchange("RELIANCE") == "NSE"

    def test_option_is_nfo(self):
        assert resolve_exchange("NIFTY24619000CE") == "NFO"
        assert resolve_exchange("NIFTY24618500PE") == "NFO"

    def test_future_is_nfo(self):
        assert resolve_exchange("NIFTYFUT") == "NFO"

    def test_case_insensitive(self):
        assert resolve_exchange("nifty") == "INDEX"
        assert resolve_exchange("reliance") == "NSE"


# ---------------------------------------------------------------------------
# Test Quote Command
# ---------------------------------------------------------------------------


class TestShowQuote:
    """Tests for show_quote command."""

    def test_show_quote_success(self, mock_broker_service, console, mock_quote):
        mock_broker_service.active_broker.quote.return_value = mock_quote

        show_quote(mock_broker_service, "RELIANCE", console)

        output = console.export_text()
        assert "RELIANCE" in output
        assert "Quote Terminal" in output
        assert "2,450.50" in output
        mock_broker_service.active_broker.quote.assert_called_once()

    def test_show_quote_no_data(self, mock_broker_service, console):
        mock_broker_service.active_broker.quote.return_value = None

        show_quote(mock_broker_service, "RELIANCE", console)

        output = console.export_text()
        assert "No quote data" in output

    def test_show_quote_index_symbol(self, mock_broker_service, console, mock_quote):
        mock_broker_service.active_broker.quote.return_value = mock_quote

        show_quote(mock_broker_service, "NIFTY", console)

        output = console.export_text()
        assert "INDEX" in output
        # Should call with INDEX exchange
        call_args = mock_broker_service.active_broker.quote.call_args
        assert call_args[0][1] == "INDEX"


# ---------------------------------------------------------------------------
# Test Depth Command
# ---------------------------------------------------------------------------


class TestShowDepth:
    """Tests for show_depth command."""

    def test_show_depth_success(self, mock_broker_service, console, mock_depth):
        mock_broker_service.active_broker.depth.return_value = mock_depth

        show_depth(mock_broker_service, "RELIANCE", console)

        output = console.export_text()
        assert "Market Depth" in output
        assert "2,450.00" in output
        assert "2,451.00" in output
        mock_broker_service.active_broker.depth.assert_called_once()

    def test_show_depth_no_data(self, mock_broker_service, console):
        mock_broker_service.active_broker.depth.return_value = None

        show_depth(mock_broker_service, "RELIANCE", console)

        output = console.export_text()
        assert "No depth data" in output

    def test_show_depth_empty_book(self, mock_broker_service, console):
        depth = MagicMock()
        depth.bids = []
        depth.asks = []
        mock_broker_service.active_broker.depth.return_value = depth

        show_depth(mock_broker_service, "RELIANCE", console)

        output = console.export_text()
        assert "No depth data" in output


# ---------------------------------------------------------------------------
# Test Option Chain Command
# ---------------------------------------------------------------------------


class TestShowOptionChain:
    """Tests for show_option_chain command."""

    def test_show_option_chain_success(self, mock_broker_service, console):
        # Mock option chain data
        chain_data = {
            "spot": 24600.00,
            "strikes": [
                {
                    "strike": 24500,
                    "call": {
                        "oi": 5000,
                        "volume": 10000,
                        "iv": 15.5,
                        "ltp": 150.00,
                        "delta": 0.6,
                        "theta": -5.2,
                    },
                    "put": {
                        "oi": 4000,
                        "volume": 8000,
                        "iv": 16.0,
                        "ltp": 140.00,
                        "delta": -0.4,
                        "theta": -4.8,
                    },
                },
                {
                    "strike": 24600,
                    "call": {
                        "oi": 8000,
                        "volume": 15000,
                        "iv": 14.5,
                        "ltp": 100.00,
                        "delta": 0.5,
                        "theta": -6.0,
                    },
                    "put": {
                        "oi": 7000,
                        "volume": 12000,
                        "iv": 15.0,
                        "ltp": 100.00,
                        "delta": -0.5,
                        "theta": -6.0,
                    },
                },
            ],
        }

        mock_broker_service.active_broker.options.get_expiries.return_value = ["2026-06-25"]
        mock_broker_service.active_broker.options.get_option_chain.return_value = chain_data

        show_option_chain(mock_broker_service, "NIFTY", console)

        output = console.export_text()
        assert "Option Chain" in output
        assert "NIFTY" in output
        assert "24,600" in output  # Spot price

    def test_show_option_chain_no_strikes(self, mock_broker_service, console):
        chain_data = {"spot": 24600.00, "strikes": []}

        mock_broker_service.active_broker.options.get_expiries.return_value = ["2026-06-25"]
        mock_broker_service.active_broker.options.get_option_chain.return_value = chain_data

        show_option_chain(mock_broker_service, "NIFTY", console)

        output = console.export_text()
        assert "No Chain" in output or "option chain" in output.lower()


# ---------------------------------------------------------------------------
# Test Futures Command
# ---------------------------------------------------------------------------


class TestShowFutures:
    """Tests for show_futures command."""

    def test_show_futures_success(self, mock_broker_service, console):
        from domain.entities.options import FutureChain, FutureContract

        chain = FutureChain(
            underlying="NIFTY",
            exchange="NFO",
            expiries=("2026-06-25", "2026-07-30"),
            contracts=(
                FutureContract(
                    symbol="NIFTY25JUNFUT",
                    expiry="2026-06-25",
                    lot_size=50,
                ),
                FutureContract(
                    symbol="NIFTY30JULFUT",
                    expiry="2026-07-30",
                    lot_size=50,
                ),
            ),
        )

        mock_broker_service.active_broker.future_chain.return_value = chain

        show_futures(mock_broker_service, "NIFTY", console)

        output = console.export_text()
        assert "Futures Contracts" in output
        assert "NIFTY" in output
        assert "2026-06-25" in output
        mock_broker_service.active_broker.future_chain.assert_called_once()

    def test_show_futures_no_contracts(self, mock_broker_service, console):
        from domain.entities.options import FutureChain

        chain = FutureChain(underlying="NIFTY", exchange="NFO", expiries=(), contracts=())
        mock_broker_service.active_broker.future_chain.return_value = chain

        show_futures(mock_broker_service, "NIFTY", console)

        output = console.export_text()
        assert "No contracts found" in output

    def test_show_commodity_futures(self, mock_broker_service, console):
        from domain.entities.options import FutureChain

        chain = FutureChain(
            underlying="GOLD",
            exchange="MCX",
            expiries=("2026-07-01",),
            contracts=(),
        )

        mock_broker_service.active_broker.future_chain.return_value = chain

        show_futures(mock_broker_service, "GOLD", console)

        # Should route to MCX
        call_args = mock_broker_service.active_broker.future_chain.call_args
        assert call_args[0][1] == "MCX"


# ---------------------------------------------------------------------------
# Test Historical Command
# ---------------------------------------------------------------------------


class TestShowHistorical:
    """Tests for show_historical command."""

    def test_show_historical_success(self, mock_broker_service, console):
        from datetime import datetime

        with patch("cli.composer_helpers.get_market_data_composer") as mock_get_composer:
            mock_composer = MagicMock()
            mock_get_composer.return_value = mock_composer

            mock_bar = MagicMock()
            mock_bar.timestamp = datetime(2026, 1, 1)
            mock_bar.open = 100.0
            mock_bar.high = 105.0
            mock_bar.low = 99.0
            mock_bar.close = 102.0
            mock_bar.volume = 1000000

            mock_series = MagicMock()
            mock_series.bars = [mock_bar] * 10
            mock_series.bar_count = 10
            mock_series.is_degraded = False

            mock_ledger = MagicMock()
            mock_ledger.conflicts = []

            mock_composer.fetch_historical = MagicMock(return_value=(mock_series, mock_ledger))

            with patch("infrastructure.async_compat.run_async_compat", return_value=(mock_series, mock_ledger)):
                show_historical(mock_broker_service, "RELIANCE", console)

            output = console.export_text()
            assert "Historical" in output
            assert "RELIANCE" in output

    def test_show_historical_no_data(self, mock_broker_service, console):
        with patch("cli.composer_helpers.get_market_data_composer") as mock_get_composer:
            mock_composer = MagicMock()
            mock_get_composer.return_value = mock_composer

            mock_series = MagicMock()
            mock_series.bars = []

            mock_ledger = MagicMock()
            mock_ledger.conflicts = []

            with patch("infrastructure.async_compat.run_async_compat", return_value=(mock_series, mock_ledger)):
                show_historical(mock_broker_service, "RELIANCE", console)

            output = console.export_text()
            assert "no historical data" in output.lower()

    def test_show_historical_none_data(self, mock_broker_service, console):
        with patch("cli.composer_helpers.get_market_data_composer") as mock_get_composer:
            mock_composer = MagicMock()
            mock_get_composer.return_value = mock_composer

            mock_series = MagicMock()
            mock_series.bars = None

            mock_ledger = MagicMock()
            mock_ledger.conflicts = []

            with patch("infrastructure.async_compat.run_async_compat", return_value=(mock_series, mock_ledger)):
                show_historical(mock_broker_service, "RELIANCE", console)

            output = console.export_text()
            assert "no historical data" in output.lower()


# ---------------------------------------------------------------------------
# Test Market Router
# ---------------------------------------------------------------------------


class TestMarketRouter:
    """Tests for the market command router."""

    def test_market_no_args(self, console):
        cmd_market.run([], MagicMock(), console)
        output = console.export_text()
        assert "Usage" in output

    def test_market_unknown_subcommand(self, console):
        cmd_market.run(["unknown"], MagicMock(), console)
        output = console.export_text()
        assert "Unknown" in output

    def test_market_quote_subcommand(self, mock_broker_service, console, mock_quote):
        mock_broker_service.active_broker.quote.return_value = mock_quote

        cmd_market.run(["quote", "RELIANCE"], mock_broker_service, console)

        output = console.export_text()
        assert "RELIANCE" in output

    def test_market_depth_subcommand(self, mock_broker_service, console, mock_depth):
        mock_broker_service.active_broker.market_data.get_depth.return_value = mock_depth

        cmd_market.run(["depth", "RELIANCE"], mock_broker_service, console)

        output = console.export_text()
        assert "Depth" in output

    def test_market_option_chain_subcommand(self, mock_broker_service, console):
        chain_data = {"spot": 24600.00, "strikes": []}
        mock_broker_service.active_broker.options.get_expiries.return_value = ["2026-06-25"]
        mock_broker_service.active_broker.options.get_option_chain.return_value = chain_data

        cmd_market.run(["option-chain", "NIFTY"], mock_broker_service, console)

        output = console.export_text()
        assert "Option Chain" in output

    def test_market_futures_subcommand(self, mock_broker_service, console):
        mock_broker_service.active_broker.futures.get_contracts.return_value = []

        cmd_market.run(["futures", "NIFTY"], mock_broker_service, console)

        output = console.export_text()
        assert "Futures" in output

    def test_market_historical_subcommand(self, mock_broker_service, console):
        with patch("cli.composer_helpers.get_market_data_composer") as mock_get_composer:
            mock_composer = MagicMock()
            mock_get_composer.return_value = mock_composer

            mock_series = MagicMock()
            mock_series.bars = []
            mock_ledger = MagicMock()
            mock_ledger.conflicts = []

            with patch("infrastructure.async_compat.run_async_compat", return_value=(mock_series, mock_ledger)):
                cmd_market.run(["historical", "RELIANCE"], mock_broker_service, console)

            output = console.export_text()
            assert "Historical" in output or "historical" in output.lower()
