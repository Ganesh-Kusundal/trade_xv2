"""Typed portfolio context tests (DR-E3).

Asserts portfolio state mutates correctly through the typed
``PortfolioContext`` and that ``PortfolioService`` / ``portfolio_service`` no
longer depend on loosely-typed ``Any``.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

from application.portfolio import PortfolioContext, PortfolioService
from domain import Balance, Position, Trade
from domain.primitives.value_objects import Money

SRC = Path(__file__).resolve().parents[4] / "src"
PORTFOLIO_SERVICE = SRC / "application/portfolio/portfolio_service.py"


def test_portfolio_service_has_no_any():
    text = PORTFOLIO_SERVICE.read_text()
    # No loosely-typed ``Any`` should remain in actual type positions.
    assert "from typing import Any" not in text
    assert "position_manager: Any" not in text
    assert "order_manager: Any" not in text
    assert "list[Any]" not in text
    # Domain types are the explicit authorities for portfolio state.
    assert "PositionStore" in text
    assert "TradeStore" in text


class _FakePositionStore:
    def __init__(self, positions: Sequence[Position]) -> None:
        self._positions = positions

    def get_positions(self) -> Sequence[Position]:
        return self._positions


class _FakeTradeStore:
    def get_trades(self, symbol: str | None = None) -> Sequence[Trade]:
        return [
            Trade(
                trade_id="t1",
                order_id="o1",
                symbol="A",
                exchange="X",
                side="BUY",
                quantity=10,
                price=Decimal("100"),
            )
        ]


def test_position_manager_mirrors_to_portfolio_context():
    """TOS-P5-022: OMS PositionManager mirrors fills into PortfolioContext."""
    from application.oms.position_manager import PositionManager
    from domain import Side

    ctx = PortfolioContext()
    pm = PositionManager(enforce_state_transitions=False, portfolio_context=ctx)
    buy = Trade(
        trade_id="t1",
        order_id="o1",
        symbol="A",
        exchange="X",
        side=Side.BUY,
        quantity=10,
        price=Decimal("100"),
    )
    pm.apply_trade(buy)
    positions = ctx.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "A"
    assert positions[0].quantity == 10


def test_apply_trade_mutates_state_correctly():
    ctx = PortfolioContext()

    buy = Trade(
        trade_id="t1",
        order_id="o1",
        symbol="A",
        exchange="X",
        side="BUY",
        quantity=10,
        price=Decimal("100"),
    )
    pos = ctx.apply_trade(buy)
    assert isinstance(pos, Position)
    assert pos.quantity == 10
    assert pos.avg_price == Money(100)
    assert pos.unrealized_pnl == Money(0)
    assert pos.realized_pnl == Money(0)

    sell = Trade(
        trade_id="t2",
        order_id="o2",
        symbol="A",
        exchange="X",
        side="SELL",
        quantity=-4,
        price=Decimal("110"),
    )
    pos = ctx.apply_trade(sell)
    assert pos.quantity == 6
    assert pos.avg_price == Money(100)
    # realized = 4 * (110 - 100) = 40
    assert pos.realized_pnl == Money(40)
    # ltp updated to fill price -> unrealized = 6 * (110 - 100) = 60
    assert pos.unrealized_pnl == Money(60)

    # The context is the single typed owner of this state.
    assert ctx.get_position("A", "X") is pos
    assert len(ctx.get_positions()) == 1
    assert ctx.total_realized_pnl() == Money(40)
    assert ctx.total_unrealized_pnl() == Money(60)


def test_apply_balance_is_typed():
    ctx = PortfolioContext()
    bal = Balance(available_balance=Decimal("5000"))
    ctx.apply_balance(bal)
    assert isinstance(ctx.balance, Balance)
    assert ctx.balance.available_balance == Decimal("5000")


def test_portfolio_service_returns_typed_summaries():
    positions = [
        Position(
            symbol="A",
            exchange="X",
            quantity=10,
            avg_price=Decimal("100"),
            ltp=Decimal("110"),
            unrealized_pnl=Decimal("100"),
            realized_pnl=Decimal("0"),
        )
    ]
    svc = PortfolioService(_FakePositionStore(positions), _FakeTradeStore())
    summary = svc.get_positions()
    assert isinstance(summary, object)
    assert summary.count == 1
    assert summary.positions[0].symbol == "A"
    assert summary.positions[0].quantity == 10

    holdings = svc.get_holdings()
    assert holdings.count == 1
    assert holdings.holdings[0].symbol == "A"

    book = svc.get_tradebook()
    assert len(book.trades) == 1
    # trades must be typed as Trade, not Any
    assert all(isinstance(t, Trade) for t in book.trades)
