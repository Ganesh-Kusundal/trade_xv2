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


# ─── Property-based tests ────────────────────────────────────────────────

from decimal import Decimal
from hypothesis import given, assume, strategies as st
from hypothesis.strategies import integers, decimals


def _make_instrument_id() -> InstrumentId:
    return InstrumentId.parse("NSE:RELIANCE")


def _make_position(qty: Decimal) -> Position:
    zero = Money(amount=Decimal("0"), currency="INR")
    return Position(
        instrument_id=_make_instrument_id(),
        quantity=Quantity(value=qty),
        avg_price=Price(value=Decimal("2500")),
        realized_pnl=zero,
        unrealized_pnl=zero,
    )


def _make_context(
    *,
    position_qty: Decimal = Decimal("0"),
    daily_pnl: Decimal = Decimal("0"),
    order_count: int = 0,
    available_margin: Decimal = Decimal("1000000"),
) -> RiskContext:
    zero = Money(amount=Decimal("0"), currency="INR")
    iid = _make_instrument_id()
    positions = {iid: _make_position(position_qty)}
    return RiskContext(
        positions=positions,
        daily_pnl=daily_pnl,
        order_count=order_count,
        available_margin=available_margin,
    )


def _make_command(
    *,
    qty: Decimal = Decimal("10"),
    side: OrderSide = OrderSide.BUY,
    price: Decimal = Decimal("2500"),
) -> PlaceOrderCommand:
    return PlaceOrderCommand(
        instrument_id=_make_instrument_id(),
        side=side,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=qty),
        price=Price(value=price),
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid4()),
    )


positive_decimal = decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1000000000"),
    allow_nan=False,
    allow_infinity=False,
    places=8,
)

positive_int = integers(min_value=0, max_value=1000000)


@given(
    order_qty=positive_decimal,
    max_qty=positive_decimal,
)
def test_order_size_rule_property(order_qty: Decimal, max_qty: Decimal) -> None:
    """OrderSizeRule: approve iff quantity <= max_qty."""
    assume(max_qty > Decimal("0"))
    rule = OrderSizeRule(max_qty=max_qty)
    result = rule.check(_make_command(qty=order_qty), _make_context())

    if order_qty > max_qty:
        assert not result.approved
        assert "order size" in result.reason.lower()
    else:
        assert result.approved


@given(
    position_qty=positive_decimal,
    order_qty=positive_decimal,
    max_qty=positive_decimal,
)
def test_position_limit_rule_property(position_qty: Decimal, order_qty: Decimal, max_qty: Decimal) -> None:
    """PositionLimitRule: approve iff |position + delta| <= max_qty."""
    assume(max_qty > Decimal("0"))
    rule = PositionLimitRule(max_qty=max_qty)
    ctx = _make_context(position_qty=position_qty)
    cmd = _make_command(qty=order_qty, side=OrderSide.BUY)

    projected = abs(position_qty + order_qty)
    result = rule.check(cmd, ctx)

    if projected > max_qty:
        assert not result.approved
        assert "position" in result.reason.lower()
    else:
        assert result.approved


@given(
    position_qty=positive_decimal,
    order_qty=positive_decimal,
    max_qty=positive_decimal,
)
def test_position_limit_sell_property(position_qty: Decimal, order_qty: Decimal, max_qty: Decimal) -> None:
    """PositionLimitRule on SELL: approve iff |position - order| <= max_qty."""
    assume(max_qty > Decimal("0"))
    assume(position_qty >= order_qty)  # Ensure we don't flip sign
    rule = PositionLimitRule(max_qty=max_qty)
    ctx = _make_context(position_qty=position_qty)
    cmd = _make_command(qty=order_qty, side=OrderSide.SELL)

    projected = abs(position_qty - order_qty)
    result = rule.check(cmd, ctx)

    if projected > max_qty:
        assert not result.approved
    else:
        assert result.approved


@given(
    daily_pnl=decimals(
        min_value=Decimal("-1000000"),
        max_value=Decimal("1000000"),
        allow_nan=False,
        allow_infinity=False,
        places=2,
    ),
    max_loss=positive_decimal,
)
def test_daily_loss_rule_property(daily_pnl: Decimal, max_loss: Decimal) -> None:
    """DailyLossRule: reject iff daily_pnl < -max_loss."""
    assume(max_loss > Decimal("0"))
    rule = DailyLossRule(max_loss=max_loss)
    ctx = _make_context(daily_pnl=daily_pnl)
    result = rule.check(_make_command(), ctx)

    if daily_pnl < -max_loss:
        assert not result.approved
        assert "daily loss" in result.reason.lower()
    else:
        assert result.approved


@given(
    order_count=positive_int,
    max_orders=positive_int,
)
def test_order_rate_rule_property(order_count: int, max_orders: int) -> None:
    """OrderRateRule: reject iff order_count >= max_orders."""
    assume(max_orders > 0)
    rule = OrderRateRule(max_orders=max_orders)
    ctx = _make_context(order_count=order_count)
    result = rule.check(_make_command(), ctx)

    if order_count >= max_orders:
        assert not result.approved
        assert "rate" in result.reason.lower() or "order count" in result.reason.lower()
    else:
        assert result.approved


@given(
    price=positive_decimal,
    qty=positive_decimal,
    max_notional=positive_decimal,
)
def test_notional_rule_property(price: Decimal, qty: Decimal, max_notional: Decimal) -> None:
    """NotionalRule: reject iff price * qty > max_notional."""
    assume(max_notional > Decimal("0"))
    from application.risk.rules import NotionalRule
    rule = NotionalRule(max_notional=max_notional)
    cmd = _make_command(qty=qty, price=price)
    result = rule.check(cmd, _make_context())

    notional = price * qty
    if notional > max_notional:
        assert not result.approved
        assert "notional" in result.reason.lower()
    else:
        assert result.approved


@given(
    order_qty=positive_decimal,
    max_qty=positive_decimal,
    max_loss=positive_decimal,
    daily_pnl=decimals(
        min_value=Decimal("-1000000"),
        max_value=Decimal("1000000"),
        allow_nan=False,
        allow_infinity=False,
        places=2,
    ),
)
def test_engine_first_failure_wins_property(
    order_qty: Decimal,
    max_qty: Decimal,
    max_loss: Decimal,
    daily_pnl: Decimal,
) -> None:
    """Engine: first failing rule's reason wins."""
    assume(max_qty > Decimal("0"))
    assume(max_loss > Decimal("0"))

    engine = RiskRulesEngine(
        [
            OrderSizeRule(max_qty=max_qty),
            DailyLossRule(max_loss=max_loss),
        ]
    )
    ctx = _make_context(daily_pnl=daily_pnl)
    cmd = _make_command(qty=order_qty)
    result = engine.check(cmd, ctx)

    order_size_fails = order_qty > max_qty
    daily_loss_fails = daily_pnl < -max_loss

    if order_size_fails or daily_loss_fails:
        assert not result.approved
        if order_size_fails:
            # OrderSizeRule is first, so its reason should win
            assert "order size" in result.reason.lower()
        else:
            # Only daily loss fails
            assert "daily loss" in result.reason.lower()
    else:
        assert result.approved


@given(
    rules_count=integers(min_value=1, max_value=10),
    all_pass=st.booleans(),
)
def test_engine_all_rules_pass_or_first_fails(rules_count: int, all_pass: bool) -> None:
    """Engine approves iff all rules pass; first failure wins."""
    rules = []
    for i in range(rules_count):
        max_qty = Decimal(str(10 * (i + 1)))
        if all_pass:
            # All rules should pass - use large limits
            rules.append(OrderSizeRule(max_qty=Decimal("1000000")))
        else:
            # First rule fails, others would pass
            if i == 0:
                rules.append(OrderSizeRule(max_qty=Decimal("1")))
            else:
                rules.append(OrderSizeRule(max_qty=Decimal("1000000")))

    engine = RiskRulesEngine(rules)
    cmd = _make_command(qty=Decimal("5"))
    result = engine.check(cmd, _make_context())

    if all_pass:
        assert result.approved
    else:
        assert not result.approved
        assert "order size" in result.reason.lower()


# Composite property: engine with all 4 rules
@given(
    order_qty=positive_decimal,
    max_qty=positive_decimal,
    position_qty=positive_decimal,
    max_position=positive_decimal,
    daily_pnl=decimals(
        min_value=Decimal("-1000000"),
        max_value=Decimal("1000000"),
        allow_nan=False,
        allow_infinity=False,
        places=2,
    ),
    max_loss=positive_decimal,
    order_count=positive_int,
    max_orders=positive_int,
)
def test_full_engine_property(
    order_qty: Decimal,
    max_qty: Decimal,
    position_qty: Decimal,
    max_position: Decimal,
    daily_pnl: Decimal,
    max_loss: Decimal,
    order_count: int,
    max_orders: int,
) -> None:
    """Full engine with all 4 rules: approves iff all pass."""
    assume(max_qty > Decimal("0"))
    assume(max_position > Decimal("0"))
    assume(max_loss > Decimal("0"))
    assume(max_orders > 0)

    engine = RiskRulesEngine(
        [
            OrderSizeRule(max_qty=max_qty),
            PositionLimitRule(max_qty=max_position),
            DailyLossRule(max_loss=max_loss),
            OrderRateRule(max_orders=max_orders),
        ]
    )
    ctx = _make_context(
        position_qty=position_qty,
        daily_pnl=daily_pnl,
        order_count=order_count,
    )
    cmd = _make_command(qty=order_qty, side=OrderSide.BUY)
    result = engine.check(cmd, ctx)

    # Check each rule
    size_pass = order_qty <= max_qty
    projected = abs(position_qty + order_qty)
    position_pass = projected <= max_position
    loss_pass = daily_pnl >= -max_loss
    rate_pass = order_count < max_orders

    all_pass = size_pass and position_pass and loss_pass and rate_pass

    if all_pass:
        assert result.approved
    else:
        assert not result.approved
        # First failure wins
        if not size_pass:
            assert "order size" in result.reason.lower()
        elif not position_pass:
            assert "position" in result.reason.lower()
        elif not loss_pass:
            assert "daily loss" in result.reason.lower()
        else:
            assert "rate" in result.reason.lower() or "order count" in result.reason.lower()
