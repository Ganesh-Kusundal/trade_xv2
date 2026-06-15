"""Integration tests for TradeXV2 CLI subcommand handlers.

These tests run against the live Dhan broker when .env.local is present.
No mock or synthetic market data is used.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console

from brokers.dhan import BrokerGateway
from cli.commands import account as cmd_account
from cli.commands import broker as cmd_broker
from cli.commands import doctor as cmd_doctor
from cli.commands import instrument as cmd_instrument
from cli.commands import market as cmd_market
from cli.commands import oms as cmd_oms
from cli.commands import portfolio as cmd_portfolio
from cli.commands import search as cmd_search
from cli.services.broker_service import BrokerService

LIVE_DHAN = Path(__file__).resolve().parent.parent.parent / ".env.local"

pytestmark = [
    pytest.mark.skipif(not LIVE_DHAN.exists(), reason=".env.local required for live Dhan CLI tests"),
]


@pytest.fixture
def services():
    broker_service = BrokerService()
    assert broker_service.is_live_dhan_active, (
        f"Expected live BrokerGateway — error: {broker_service.dhan_load_error}"
    )
    gw = broker_service.active_broker
    assert isinstance(gw, BrokerGateway)
    return broker_service


def test_broker_command(services):
    broker_service = services
    console = Console(record=True)
    cmd_broker.run(["list"], broker_service, console)
    output = console.export_text()
    assert "Dhan" in output or "dhan" in output


def test_account_command(services):
    broker_service = services
    console = Console(record=True)
    cmd_account.run([], broker_service, console)
    output = console.export_text()
    assert "Balance" in output or "Margin" in output or "Available" in output or "Fund" in output


@pytest.mark.integration
def test_portfolio_commands(services):
    broker_service = services
    console = Console(record=True)
    cmd_portfolio.show_holdings(broker_service, console)
    output_holdings = console.export_text()
    assert "Holding" in output_holdings or "Demat" in output_holdings or "Symbol" in output_holdings

    pos_console = Console(record=True)
    cmd_portfolio.show_positions(broker_service, pos_console)
    output_pos = pos_console.export_text()
    assert "Position" in output_pos or "Symbol" in output_pos


def test_oms_commands(services):
    broker_service = services
    console = Console(record=True)
    cmd_oms.show_orders(broker_service, console)
    assert "Order" in console.export_text()

    trades_console = Console(record=True)
    cmd_oms.show_trades(broker_service, trades_console)
    assert "Trade" in trades_console.export_text()


def test_market_data_commands(services):
    broker_service = services
    console = Console(record=True)

    cmd_market.show_quote(broker_service, "RELIANCE", console)
    output = console.export_text()
    assert "Quote" in output or "LTP" in output or "RELIANCE" in output


def test_doctor_command(services):
    broker_service = services
    console = Console(record=True)
    cmd_doctor.run([], broker_service, console)
    output = console.export_text()
    assert "Diagnostics" in output or "Doctor" in output or "Check" in output


def test_instrument_commands(services):
    broker_service = services
    console = Console(record=True)
    cmd_search.run(["RELIANCE"], broker_service, console)
    search_out = console.export_text()
    assert "RELIANCE" in search_out

    inst_console = Console(record=True)
    cmd_instrument.run(["RELIANCE"], broker_service, inst_console)
    inst_out = inst_console.export_text()
    assert "RELIANCE" in inst_out or "Instrument" in inst_out or "Mapping" in inst_out
