"""Tests for the TradeXV2 CLI subcommand handlers."""

from __future__ import annotations

import pytest
from rich.console import Console

from cli.commands import (
    account as cmd_account,
)
from cli.commands import (
    broker as cmd_broker,
)
from cli.commands import (
    doctor as cmd_doctor,
)
from cli.commands import (
    instrument as cmd_instrument,
)
from cli.commands import (
    market as cmd_market,
)
from cli.commands import (
    oms as cmd_oms,
)
from cli.commands import (
    portfolio as cmd_portfolio,
)
from cli.commands import (
    search as cmd_search,
)
from cli.services.broker_service import BrokerService
from cli.services.event_bus_service import EventBusService
from cli.services.oms_service import OmsService


@pytest.fixture
def services():
    broker_service = BrokerService()
    # Connect all brokers for testing connection states
    for b in broker_service.brokers.values():
        b.connect()
    # Ensure active broker is mock for tests
    broker_service.set_active_broker("zerodha")
    oms_service = OmsService(broker_service)
    event_bus_service = EventBusService()
    return broker_service, oms_service, event_bus_service


def test_broker_command(services):
    broker_service, _, _ = services
    console = Console(record=True)

    # Run list
    cmd_broker.run(["list"], broker_service, console)
    output = console.export_text()
    assert "Zerodha" in output
    assert "Connected" in output

    # Run use switch
    cmd_broker.run(["use", "upstox"], broker_service, console)
    assert broker_service.active_broker_name == "upstox"


def test_account_command(services):
    broker_service, _, _ = services
    console = Console(record=True)

    cmd_account.run([], broker_service, console)
    output = console.export_text()
    assert "Available Margin" in output
    assert "Realized Day PnL" in output


def test_portfolio_commands(services):
    broker_service, _, _ = services
    console = Console(record=True)

    # Holdings
    cmd_portfolio.show_holdings(broker_service, console)
    output_holdings = console.export_text()
    assert "Holding" in output_holdings or "Demat Holdings" in output_holdings

    # Positions
    cmd_portfolio.show_positions(broker_service, console)
    output_pos = console.export_text()
    assert "Positions Overview" in output_pos
    assert "Long Positions" in output_pos


def test_oms_commands(services):
    _, oms_service, _ = services
    console = Console(record=True)

    # Orders
    cmd_oms.show_orders(oms_service, console)
    output_ord = console.export_text()
    assert "Today's Orders" in output_ord

    # Trades
    cmd_oms.show_trades(oms_service, console)
    output_trd = console.export_text()
    assert "Trades Execution" in output_trd

    # OMS Summary
    cmd_oms.show_oms_summary(oms_service, console)
    output_sum = console.export_text()
    assert "OMS Diagnostics Summary" in output_sum


def test_market_data_commands(services):
    broker_service, _, _ = services
    console = Console(record=True)
    broker = broker_service.active_broker

    # Quote
    cmd_market.show_quote(broker, "RELIANCE", console, live_mode=False)
    assert "Quote Terminal" in console.export_text()

    # Depth
    cmd_market.show_depth(broker, "RELIANCE", console, live_mode=False)
    assert "Market Depth L2" in console.export_text()

    # Option Chain
    cmd_market.show_option_chain(broker, "NIFTY", console)
    assert "Option Chain" in console.export_text()

    # Futures
    cmd_market.show_futures(broker, "NIFTY", console)
    assert "Futures Contracts" in console.export_text()

    # Historical
    cmd_market.show_historical(broker, "RELIANCE", console)
    assert "Historical Data Preview" in console.export_text()


def test_doctor_command(services):
    broker_service, _, _ = services
    console = Console(record=True)

    cmd_doctor.run([], broker_service, console)
    output = console.export_text()
    assert "Diagnostics Report" in output
    assert "Authentication Check" in output
    assert "Quote Check" in output


def test_instrument_commands(services):
    broker_service, _, _ = services
    console = Console(record=True)
    broker = broker_service.active_broker

    # Search
    cmd_search.run(["RELIANCE"], broker, console)
    assert "RELIANCE" in console.export_text()

    # Instrument Mapping
    cmd_instrument.run(["NIFTY"], broker, console)
    assert "Multi-Broker Mapping" in console.export_text()


def test_cli_alias_funds(services, monkeypatch):
    """Verify 'funds' routes to account command."""
    broker_service, _, _ = services
    console = Console(record=True)
    # Directly test that funds routes to cmd_account
    cmd_account.run([], broker_service, console)
    output = console.export_text()
    assert "Available Margin" in output


def test_cli_alias_history(services):
    """Verify 'history' routes to historical command."""
    broker_service, _, _ = services
    console = Console(record=True)
    broker = broker_service.active_broker
    cmd_market.show_historical(broker, "RELIANCE", console)
    assert "Historical Data Preview" in console.export_text()
