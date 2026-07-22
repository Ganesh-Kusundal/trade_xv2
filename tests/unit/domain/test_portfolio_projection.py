"""P2: shared portfolio projection parity."""

from __future__ import annotations

from decimal import Decimal

from application.oms.position_manager import PositionManager
from domain import Side
from domain.entities import Position, Trade
from application.services.simulation_orchestrator import PortfolioProjector, project_trade


def _trade(symbol: str, side: Side, qty: int, price: str, tid: str) -> Trade:
    return Trade(
        trade_id=tid,
        order_id=f"ord-{tid}",
        symbol=symbol,
        exchange="NSE",
        side=side,
        quantity=qty,
        price=Decimal(price),
        trade_value=Decimal(price) * qty,
    )


def test_project_trade_matches_position_with_fill():
    pos = Position(symbol="RELIANCE", exchange="NSE")
    trade = _trade("RELIANCE", Side.BUY, 10, "2500", "t1")
    via_helper = project_trade(pos, trade)
    via_entity = pos.with_fill(10, Decimal("2500"))
    assert via_helper.quantity == via_entity.quantity
    assert via_helper.avg_price == via_entity.avg_price


def test_projector_matches_position_manager():
    trades = [
        _trade("RELIANCE", Side.BUY, 10, "2500", "t1"),
        _trade("RELIANCE", Side.BUY, 5, "2600", "t2"),
        _trade("RELIANCE", Side.SELL, 8, "2700", "t3"),
    ]
    projector = PortfolioProjector()
    manager = PositionManager()

    for trade in trades:
        p_pos = projector.apply_trade(trade)
        m_pos = manager.apply_trade(trade)
        assert p_pos.quantity == m_pos.quantity
        assert p_pos.avg_price == m_pos.avg_price
        assert p_pos.realized_pnl == m_pos.realized_pnl
