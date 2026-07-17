"""P2-analytics: single Trade/Position for simulation."""
from analytics.shared.trade_types import SimTrade, SimPosition
from domain.enums import Side
from decimal import Decimal

def test_sim_trade_construction():
    trade = SimTrade(
        trade_id="t1",
        symbol="RELIANCE",
        side=Side.BUY,
        quantity=100,
        price=Decimal("2500"),
    )
    assert trade.trade_id == "t1"
    assert trade.price == Decimal("2500")

def test_sim_position_construction():
    pos = SimPosition(
        symbol="RELIANCE",
        side=Side.BUY,
        quantity=100,
        avg_price=Decimal("2500"),
    )
    assert pos.symbol == "RELIANCE"
    assert pos.avg_price == Decimal("2500")
