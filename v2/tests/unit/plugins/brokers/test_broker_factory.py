"""Tests for broker_factory Protocol enforcement and ws_factory parameter."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from config.schema import AppConfig, Environment
from domain.enums import BrokerId
from runtime.broker_factory import build_broker_adapter


class TestBrokerFactoryProtocolEnforcement:
    """build_broker_adapter should enforce BrokerAdapter Protocol at runtime."""

    def test_paper_gateway_satisfies_protocol(self) -> None:
        """Paper broker gateway should pass Protocol check."""
        cfg = AppConfig(environment=Environment.PAPER, broker=BrokerId.PAPER)
        gateway = build_broker_adapter(cfg)
        # Should not raise
        assert gateway is not None

    def test_ws_factory_parameter_accepted(self) -> None:
        """build_broker_adapter should accept ws_factory parameter."""
        cfg = AppConfig(environment=Environment.PAPER, broker=BrokerId.PAPER)
        mock_ws = MagicMock()
        gateway = build_broker_adapter(cfg, ws_factory=mock_ws)
        # Should not raise
        assert gateway is not None


class TestPaperGatewayMethodAliases:
    """PaperGateway should have method aliases for Dhan/Upstox parity."""

    def test_ltp_alias(self) -> None:
        """ltp() should be an alias for get_ltp()."""
        from plugins.brokers.paper.gateway import PaperGateway
        from domain.value_objects import InstrumentId, Price

        gw = PaperGateway()
        # Use set_quote to seed data properly
        iid = InstrumentId.parse("NSE:TEST")
        gw.set_quote(iid, Decimal("100"), Decimal("102"))
        price = gw.ltp(iid)
        assert isinstance(price, Price)
        assert price.value == Decimal("101")  # midpoint

    def test_depth_alias(self) -> None:
        """depth() should be an alias for get_depth()."""
        from plugins.brokers.paper.gateway import PaperGateway
        from domain.entities import MarketDepth
        from domain.value_objects import InstrumentId

        gw = PaperGateway()
        iid = InstrumentId.parse("NSE:TEST")
        # Seed a quote first
        gw.set_quote(iid, Decimal("100"), Decimal("102"))
        depth = gw.depth(iid)
        assert isinstance(depth, MarketDepth)

    def test_history_alias(self) -> None:
        """history() should be an alias for get_history()."""
        from plugins.brokers.paper.gateway import PaperGateway
        from domain.value_objects import InstrumentId, TimeFrame
        from datetime import datetime

        gw = PaperGateway()
        iid = InstrumentId.parse("NSE:TEST")
        tf = TimeFrame(value="1m")
        result = gw.history(iid, tf, datetime.now(), datetime.now())
        assert result == []

    def test_get_balance_alias(self) -> None:
        """get_balance() should be an alias for get_funds()."""
        from plugins.brokers.paper.gateway import PaperGateway
        from domain.entities import Account

        gw = PaperGateway()
        balance = gw.get_balance()
        assert isinstance(balance, Account)

    def test_authenticate_returns_true(self) -> None:
        """authenticate() should always return True for paper broker."""
        from plugins.brokers.paper.gateway import PaperGateway

        gw = PaperGateway()
        assert gw.authenticate() is True

    def test_describe_returns_broker_info(self) -> None:
        """describe() should return broker metadata."""
        from plugins.brokers.paper.gateway import PaperGateway

        gw = PaperGateway()
        info = gw.describe()
        assert info["broker"] == "paper"
        assert info["type"] == "simulated"

    def test_get_holdings_returns_positions(self) -> None:
        """get_holdings() should return positions."""
        from plugins.brokers.paper.gateway import PaperGateway

        gw = PaperGateway()
        holdings = gw.get_holdings()
        assert isinstance(holdings, list)

    def test_get_trade_book_returns_filled_orders(self) -> None:
        """get_trade_book() should return filled orders."""
        from plugins.brokers.paper.gateway import PaperGateway

        gw = PaperGateway()
        trades = gw.get_trade_book()
        assert isinstance(trades, list)

    def test_search_returns_instruments(self) -> None:
        """search() should search instruments."""
        from plugins.brokers.paper.gateway import PaperGateway

        gw = PaperGateway()
        results = gw.search("RELIANCE")
        assert isinstance(results, list)
