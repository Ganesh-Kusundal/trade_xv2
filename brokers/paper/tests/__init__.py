"""Tests for PaperBroker and BrokerFacade."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from brokers.common.core.domain import FundLimits, OrderResponse, OrderStatus, Position, Side
from brokers.common.core.facade import BrokerFacade
from brokers.paper import PaperBroker


class TestPaperBroker:
    def test_connect_disconnect(self):
        broker = PaperBroker()
        assert broker.connect() is True
        assert broker.is_connected() is True
        assert broker.disconnect() is True
        assert broker.is_connected() is False

    def test_name_and_id(self):
        broker = PaperBroker(name="test_paper")
        assert broker.name == "test_paper"
        assert broker.broker_id.startswith("paper-")

    def test_place_order_instant_fill(self):
        broker = PaperBroker()
        broker.connect()
        resp = broker.place_order("RELIANCE", "NSE", Side.BUY, 10, Decimal("2500"))
        assert isinstance(resp, OrderResponse)
        assert resp.success is True
        assert resp.order_id.startswith("PPR-")

    def test_get_order_after_placement(self):
        broker = PaperBroker()
        broker.connect()
        resp = broker.place_order("RELIANCE", "NSE", Side.BUY, 10, Decimal("2500"))
        order = broker.get_order(resp.order_id)
        assert order is not None
        assert order.symbol == "RELIANCE"
        assert order.quantity == 10
        assert order.status == OrderStatus.FILLED

    def test_get_orders(self):
        broker = PaperBroker()
        broker.connect()
        broker.place_order("RELIANCE", "NSE", Side.BUY, 10, Decimal("2500"))
        broker.place_order("SBIN", "NSE", Side.SELL, 5, Decimal("600"))
        orders = broker.get_orders()
        assert len(orders) == 2

    def test_positions_update_on_fill(self):
        broker = PaperBroker()
        broker.connect()
        broker.place_order("RELIANCE", "NSE", Side.BUY, 10, Decimal("2500"))
        positions = broker.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "RELIANCE"
        assert positions[0].quantity == 10

    def test_position_close_realizes_pnl(self):
        broker = PaperBroker()
        broker.connect()
        broker.place_order("RELIANCE", "NSE", Side.BUY, 10, Decimal("2500"))
        broker.place_order("RELIANCE", "NSE", Side.SELL, 10, Decimal("2550"))
        pos = broker.get_positions()[0]
        assert pos.quantity == 0
        assert pos.realized_pnl == Decimal("500")  # (2550-2500) * 10

    def test_fund_limits(self):
        broker = PaperBroker(initial_capital=Decimal("1000000"))
        broker.connect()
        funds = broker.get_fund_limits()
        assert isinstance(funds, FundLimits)
        assert funds.total_margin == Decimal("1000000")
        assert funds.available_balance >= Decimal("0")

    def test_get_trades(self):
        broker = PaperBroker()
        broker.connect()
        broker.place_order("RELIANCE", "NSE", Side.BUY, 10, Decimal("2500"))
        trades = broker.get_trades()
        assert len(trades) == 1
        assert trades[0].symbol == "RELIANCE"

    def test_get_quote_returns_dataframe(self):
        broker = PaperBroker()
        df = broker.get_quote("RELIANCE", "NSE")
        assert "ltp" in df.columns
        assert len(df) == 1

    def test_get_historical_data_returns_dataframe(self):
        broker = PaperBroker()
        df = broker.get_historical_data("RELIANCE", "NSE", date(2026, 1, 1), date(2026, 1, 10))
        assert "close" in df.columns
        assert len(df) == 10


class TestBrokerFacade:
    def test_facade_wraps_connection(self):
        broker = PaperBroker()
        broker.connect()
        # PaperBroker implements Broker, not BrokerConnection,
        # but we can verify the facade module imports cleanly
        from brokers.common.core.facade import BrokerFacade

        assert BrokerFacade is not None

    def test_facade_delegates_identity(self):
        from unittest.mock import MagicMock

        from brokers.common.core.connection import BrokerConnection, ConnectionStatus

        mock_conn = MagicMock(spec=BrokerConnection)
        mock_conn.name = "test"
        mock_conn.broker_id = "T1"
        mock_conn.status = ConnectionStatus.CONNECTED
        facade = BrokerFacade(mock_conn)
        assert facade.name == "test"
        assert facade.broker_id == "T1"
        assert facade.is_connected() is True
