"""PositionManager: buy creates position; sell reduces; realized PnL."""

from datetime import UTC, datetime
from decimal import Decimal

from application.oms.position_manager import PositionManager
from application.oms.trading_cache import TradingCache
from domain.entities import Trade
from domain.enums import OrderSide
from domain.value_objects import InstrumentId, Money, OrderId, Price, Quantity


def test_buy_fill_creates_position() -> None:
    cache = TradingCache()
    pm = PositionManager(cache)
    iid = InstrumentId.parse("NSE:RELIANCE")
    trade = Trade(
        trade_id="t1",
        order_id=OrderId(value="o1"),
        instrument_id=iid,
        price=Price(value=Decimal("100")),
        quantity=Quantity(value=Decimal("10")),
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 2, tzinfo=UTC),
    )
    pos = pm.apply_trade(trade)
    assert pos.quantity.value == Decimal("10")
    assert pos.avg_price.value == Decimal("100")
    assert pos.realized_pnl.amount == Decimal("0")
    assert cache.get_position(iid) is pos


def test_sell_reduces_position_and_realizes_pnl() -> None:
    cache = TradingCache()
    pm = PositionManager(cache)
    iid = InstrumentId.parse("NSE:RELIANCE")
    pm.apply_trade(
        Trade(
            trade_id="t1",
            order_id=OrderId(value="o1"),
            instrument_id=iid,
            price=Price(value=Decimal("100")),
            quantity=Quantity(value=Decimal("10")),
            side=OrderSide.BUY,
            timestamp=datetime(2024, 1, 2, tzinfo=UTC),
        )
    )
    pos = pm.apply_trade(
        Trade(
            trade_id="t2",
            order_id=OrderId(value="o2"),
            instrument_id=iid,
            price=Price(value=Decimal("110")),
            quantity=Quantity(value=Decimal("4")),
            side=OrderSide.SELL,
            timestamp=datetime(2024, 1, 2, 10, tzinfo=UTC),
        )
    )
    assert pos.quantity.value == Decimal("6")
    assert pos.avg_price.value == Decimal("100")
    assert pos.realized_pnl == Money(amount=Decimal("40"), currency="INR")
