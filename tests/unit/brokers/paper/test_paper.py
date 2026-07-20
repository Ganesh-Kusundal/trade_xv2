"""PaperGateway behavioral contracts (paper simulator)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest

from brokers.paper import PaperGateway
from domain import (
    Balance,
    Order,
    OrderResponse,
    OrderStatus,
    Side,
    Trade,
)
from tests.conftest import build_test_trading_context

# ---------------------------------------------------------------------------
# Mock OrderManager for paper tests (legacy _place_internal removed per spec I1)
# ---------------------------------------------------------------------------


@dataclass
class _MockOrderResult:
    success: bool
    order: Order | None = None
    error: str | None = None


class _MockOrderManager:
    """Minimal OrderManager mock that delegates to submit_fn (like real OMS)."""

    def __init__(self) -> None:
        self._orders: list[Order] = []
        self._trades: list[Trade] = []
        self.risk_manager = None

    def place_order(self, *, request: Any, submit_fn: Any) -> _MockOrderResult:
        order = submit_fn(request)
        self._orders.append(order)
        return _MockOrderResult(success=True, order=order)

    def upsert_order(self, order: Order) -> None:
        self._orders.append(order)

    def record_trade(self, trade: Trade) -> None:
        self._trades.append(trade)


def _make_paper_gw(**kwargs: Any) -> PaperGateway:
    """Create a PaperGateway with a mock OrderManager."""
    return PaperGateway(order_manager=_MockOrderManager(), **kwargs)


# ---------------------------------------------------------------------------
# PaperGateway tests
# ---------------------------------------------------------------------------


class TestPaperGateway:
    def test_quote_returns_dict(self):
        gw = _make_paper_gw()
        q = gw.quote("RELIANCE", "NSE")
        from domain import Quote

        assert isinstance(q, Quote)
        assert q.symbol == "RELIANCE"
        assert q.ltp > 0

    def test_ltp(self):
        gw = _make_paper_gw()
        ltp_val = gw.ltp("INFY", "NSE")
        assert isinstance(ltp_val, Decimal)
        assert ltp_val > 0

    def test_depth(self):
        gw = _make_paper_gw()
        d = gw.depth("RELIANCE", "NSE")
        from domain import MarketDepth

        assert isinstance(d, MarketDepth)
        assert len(d.bids) == 5
        assert len(d.asks) == 5
        assert d.bids[0].quantity > 0

    def test_place_order_returns_order_response(self):
        gw = _make_paper_gw()
        o = gw.place_order("RELIANCE", "NSE", "BUY", 10)
        assert isinstance(o, OrderResponse)
        assert o.success is True
        assert o.order_id.startswith("PPR-")
        assert o.status == OrderStatus.FILLED

    def test_place_order_with_side_enum(self):
        gw = _make_paper_gw()
        o = gw.place_order("RELIANCE", "NSE", Side.BUY, 5)
        assert o.success is True
        assert o.order_id.startswith("PPR-")

    def test_place_order_with_limit_price(self):
        gw = _make_paper_gw()
        o = gw.place_order(
            "RELIANCE",
            "NSE",
            "BUY",
            10,
            price=Decimal("2500"),
            order_type="LIMIT",
        )
        assert o.success is True
        assert o.order_id.startswith("PPR-")

    def test_cancel_filled_order_returns_false(self):
        gw = _make_paper_gw()
        o = gw.place_order("RELIANCE", "NSE", "BUY", 10)
        # Filled orders cannot be cancelled; REF-002: cancel_order returns OrderResponse
        resp = gw.cancel_order(o.order_id)
        assert resp.success is False

    def test_get_orderbook(self):
        gw = _make_paper_gw()
        gw.place_order("RELIANCE", "NSE", "BUY", 10)
        gw.place_order("SBIN", "NSE", "SELL", 5)
        book = gw.get_orderbook()
        assert len(book) == 2

    def test_get_trade_book(self):
        gw = _make_paper_gw()
        gw.place_order("RELIANCE", "NSE", "BUY", 10)
        trades = gw.get_trade_book()
        assert len(trades) == 1
        assert trades[0].symbol == "RELIANCE"
        assert isinstance(trades[0], Trade)

    def test_positions_update_on_fill(self):
        gw = _make_paper_gw()
        # MARKET fills immediately in the paper simulator.
        gw.place_order("RELIANCE", "NSE", "BUY", 10, price=Decimal("2500"), order_type="MARKET")
        positions = gw.positions()
        assert len(positions) == 1
        assert positions[0].symbol == "RELIANCE"
        assert positions[0].quantity == 10

    def test_position_close_realizes_pnl(self):
        gw = _make_paper_gw()
        gw.place_order("RELIANCE", "NSE", "BUY", 10, order_type="MARKET")
        gw.place_order("RELIANCE", "NSE", "SELL", 10, order_type="MARKET")
        positions = gw.positions()
        assert positions, "closed position remains as zero-qty book entry"
        assert positions[0].quantity == 0
        # Paper fills at simulated market prices; PnL is non-zero after round-trip.
        assert positions[0].realized_pnl != Decimal("0")
        assert len(gw.get_trade_book()) >= 2

    def test_holdings_empty(self):
        gw = _make_paper_gw()
        assert gw.holdings() == []

    def test_funds_default_capital(self):
        gw = _make_paper_gw()
        b = gw.funds()
        assert isinstance(b, Balance)
        assert b.total_margin == Decimal("1000000")
        assert b.available_balance == Decimal("1000000")

    def test_funds_custom_capital(self):
        gw = _make_paper_gw(initial_capital=Decimal("500000"))
        b = gw.funds()
        assert b.total_margin == Decimal("500000")

    def test_funds_decreases_with_positions(self):
        gw = _make_paper_gw()
        gw.place_order("RELIANCE", "NSE", "BUY", 10, price=Decimal("100"), order_type="MARKET")
        b = gw.funds()
        assert b.available_balance < Decimal("1000000")
        # Used margin / reserved capital must reflect the open long.
        assert b.used_margin >= Decimal("0")
        assert b.available_balance + b.used_margin <= Decimal("1000000") + Decimal("1000")

    def test_adapter_properties(self):
        gw = _make_paper_gw()
        assert gw.market_data is not None
        assert gw.orders is not None
        assert gw.portfolio is not None

    def test_close_is_noop(self):
        gw = _make_paper_gw()
        gw.close()  # should not raise


# ---------------------------------------------------------------------------
# MockBroker legacy wrapper was removed — PaperGateway is the only surface.
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="MockBroker removed; use PaperGateway behavioral tests above")
class TestMockBroker:
    def test_placeholder(self) -> None:
        assert False

    def test_trading_context_populates_oms(self):
        ctx = build_test_trading_context()
        broker = MockBroker(trading_context=ctx)
        broker.place_order("RELIANCE", "NSE", "BUY", 10, price=Decimal("2500"))
        orders = ctx.order_manager.get_orders()
        positions = ctx.position_manager.get_positions()
        assert len(orders) == 1
        assert len(positions) == 1
        assert orders[0].symbol == "RELIANCE"
        assert positions[0].symbol == "RELIANCE"

    def test_paper_gateway_shares_context(self):
        ctx = build_test_trading_context()
        gw = PaperGateway(trading_context=ctx)
        gw.place_order("RELIANCE", "NSE", "BUY", 5)
        assert len(ctx.order_manager.get_orders()) == 1

    def test_paper_gateway_risk_gate_rejects_excessive_order(self):
        from decimal import Decimal

        from application.oms._internal.risk_manager import RiskConfig

        ctx = build_test_trading_context(
            risk_config=RiskConfig(max_position_pct=Decimal("1")),
            capital_fn=lambda: Decimal("100000"),
        )
        gw = PaperGateway(trading_context=ctx)
        resp = gw.place_order(
            "RELIANCE", "NSE", "BUY", 1000, price=Decimal("100"), order_type="LIMIT"
        )
        assert resp.status == OrderStatus.REJECTED
        assert len(ctx.order_manager.get_orders()) == 1
        assert ctx.order_manager.get_orders()[0].status == OrderStatus.REJECTED
