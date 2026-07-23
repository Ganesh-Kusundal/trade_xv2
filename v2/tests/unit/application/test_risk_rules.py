"""RiskRulesEngine: first failure wins; built-in rules enforce limits."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from application.risk.context import RiskCheckResult, RiskContext
from application.risk.rules import (
    DailyLossRule,
    OrderRateRule,
    OrderSizeRule,
    PositionLimitRule,
    RiskRulesEngine,
)
from domain.commands import PlaceOrderCommand
from domain.entities import Position
from domain.enums import OrderSide, OrderType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, Money, Price, Quantity


def _cmd(qty: str = "10", side: OrderSide = OrderSide.BUY) -> PlaceOrderCommand:
    return PlaceOrderCommand(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=side,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal(qty)),
        price=Price(value=Decimal("2500")),
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid4()),
    )


def _ctx(
    *,
    position_qty: str = "0",
    daily_pnl: str = "0",
    order_count: int = 0,
    available_margin: str = "1000000",
) -> RiskContext:
    zero = Money(amount=Decimal("0"), currency="INR")
    iid = InstrumentId.parse("NSE:RELIANCE")
    positions = {
        iid: Position(
            instrument_id=iid,
            quantity=Quantity(value=Decimal(position_qty)),
            avg_price=Price(value=Decimal("2500")),
            realized_pnl=zero,
            unrealized_pnl=zero,
        )
    }
    return RiskContext(
        positions=positions,
        daily_pnl=Decimal(daily_pnl),
        order_count=order_count,
        available_margin=Decimal(available_margin),
    )


def test_order_size_rule_rejects_oversize() -> None:
    rule = OrderSizeRule(max_qty=Decimal("100"))
    result = rule.check(_cmd(qty="150"), _ctx())
    assert isinstance(result, RiskCheckResult)
    assert not result.approved
    assert "order size" in result.reason.lower()


def test_order_size_rule_approves_within_limit() -> None:
    rule = OrderSizeRule(max_qty=Decimal("100"))
    result = rule.check(_cmd(qty="50"), _ctx())
    assert result.approved


def test_position_limit_rule_rejects_projected_breach() -> None:
    rule = PositionLimitRule(max_qty=Decimal("100"))
    result = rule.check(_cmd(qty="20"), _ctx(position_qty="90"))
    assert not result.approved
    assert "position" in result.reason.lower()


def test_daily_loss_rule_rejects_when_breached() -> None:
    rule = DailyLossRule(max_loss=Decimal("50000"))
    result = rule.check(_cmd(), _ctx(daily_pnl="-50001"))
    assert not result.approved
    assert "daily loss" in result.reason.lower()


def test_order_rate_rule_rejects_when_count_exceeded() -> None:
    rule = OrderRateRule(max_orders=10)
    result = rule.check(_cmd(), _ctx(order_count=10))
    assert not result.approved
    assert "rate" in result.reason.lower() or "order count" in result.reason.lower()


def test_engine_first_failure_wins() -> None:
    engine = RiskRulesEngine(
        [
            OrderSizeRule(max_qty=Decimal("5")),  # fails first
            DailyLossRule(max_loss=Decimal("1")),  # would also fail
        ]
    )
    result = engine.check(_cmd(qty="100"), _ctx(daily_pnl="-999"))
    assert not result.approved
    assert "order size" in result.reason.lower()


def test_engine_all_pass() -> None:
    engine = RiskRulesEngine(
        [
            OrderSizeRule(max_qty=Decimal("100")),
            PositionLimitRule(max_qty=Decimal("500")),
            DailyLossRule(max_loss=Decimal("50000")),
            OrderRateRule(max_orders=100),
        ]
    )
    result = engine.check(_cmd(qty="10"), _ctx())
    assert result.approved
    assert result.reason is None or result.reason == ""
