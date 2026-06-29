"""Tests for portfolio service."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from application.portfolio.portfolio_service import (
    PortfolioService,
)


def _make_position(
    symbol: str = "RELIANCE",
    quantity: int = 10,
    avg_price: float = 2500.0,
    ltp: float = 2600.0,
    unrealized_pnl: float = 1000.0,
    realized_pnl: float = 0.0,
):
    pos = MagicMock()
    pos.symbol = symbol
    pos.exchange = "NSE"
    pos.quantity = quantity
    pos.avg_price = Decimal(str(avg_price))
    pos.ltp = Decimal(str(ltp))
    pos.unrealized_pnl = Decimal(str(unrealized_pnl))
    pos.realized_pnl = Decimal(str(realized_pnl))
    return pos


def _make_position_manager(positions=None):
    pm = MagicMock()
    pm.get_positions.return_value = positions or []
    return pm


class TestGetPositions:
    def test_empty_positions(self):
        pm = _make_position_manager([])
        svc = PortfolioService(position_manager=pm)
        result = svc.get_positions()
        assert result.count == 0
        assert result.total_pnl == 0.0

    def test_single_position_pnl(self):
        pos = _make_position(quantity=10, avg_price=2500, ltp=2600, unrealized_pnl=1000)
        pm = _make_position_manager([pos])
        svc = PortfolioService(position_manager=pm)
        result = svc.get_positions()
        assert result.count == 1
        assert result.total_pnl == 1000.0

    def test_filter_open_positions(self):
        pos_open = _make_position("RELIANCE", quantity=10)
        pos_closed = _make_position("TCS", quantity=0)
        pm = _make_position_manager([pos_open, pos_closed])
        svc = PortfolioService(position_manager=pm)
        result = svc.get_positions(status_filter="open")
        assert result.count == 1
        assert result.positions[0].symbol == "RELIANCE"

    def test_pnl_percentage(self):
        pos = _make_position(quantity=10, avg_price=2500, unrealized_pnl=250)
        pm = _make_position_manager([pos])
        svc = PortfolioService(position_manager=pm)
        result = svc.get_positions()
        # pnl_pct = 250 / (2500 * 10) * 100 = 1.0%
        assert result.positions[0].pnl_pct == pytest.approx(1.0)


class TestGetHoldings:
    def test_empty_holdings(self):
        pm = _make_position_manager([])
        svc = PortfolioService(position_manager=pm)
        result = svc.get_holdings()
        assert result.count == 0
        assert result.total_pnl == 0.0

    def test_holding_pnl(self):
        pos = _make_position(quantity=10, avg_price=2500, ltp=2600)
        pm = _make_position_manager([pos])
        svc = PortfolioService(position_manager=pm)
        result = svc.get_holdings()
        assert result.count == 1
        assert result.holdings[0].pnl == pytest.approx(1000.0)
        assert result.holdings[0].invested_value == pytest.approx(25000.0)
        assert result.holdings[0].current_value == pytest.approx(26000.0)
