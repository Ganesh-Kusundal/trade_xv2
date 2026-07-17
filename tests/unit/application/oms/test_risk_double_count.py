"""R3: partial fill must reduce pending, not double-count."""
from decimal import Decimal
from application.oms._internal.margin_checker import MarginChecker
from application.oms._internal.risk_types import RiskConfig
from domain import Order, Side, OrderStatus, OrderType


def make_order(correlation_id: str = "corr-1", quantity: int = 100) -> Order:
    return Order(
        order_id="order-1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        status=OrderStatus.OPEN,
        correlation_id=correlation_id,
    )


def test_partial_fill_reduces_pending():
    config = RiskConfig(max_gross_exposure_pct=100)
    checker = MarginChecker(config)
    order = make_order()
    checker.reserve_pending(order, notional=Decimal("100000"))
    assert checker.pending_gross() == Decimal("100000")
    checker.reduce_pending(order.correlation_id, filled_quantity=50, price=Decimal("2000"))
    assert checker.pending_gross() == Decimal("0")


def test_partial_fill_preserves_remaining_pending():
    config = RiskConfig(max_gross_exposure_pct=100)
    checker = MarginChecker(config)
    order = make_order(quantity=100)
    checker.reserve_pending(order, notional=Decimal("200000"))
    assert checker.pending_gross() == Decimal("200000")
    checker.reduce_pending(order.correlation_id, filled_quantity=30, price=Decimal("2000"))
    assert checker.pending_gross() == Decimal("140000")
