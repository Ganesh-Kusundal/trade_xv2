"""RiskManager + RiskRules TDD tests per spec 09-risk-and-safety.md."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4


from application.risk.context import RiskContext
from application.risk.risk_manager import RiskManager
from application.risk.rules import (
    DailyLossRule,
    NotionalRule,
    OrderSizeRule,
)
from domain.commands import PlaceOrderCommand
from domain.entities import Position
from domain.enums import OrderSide, OrderType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, Money, Price, Quantity


def _cmd(
    qty: str = "10",
    price: str = "2500",
    side: OrderSide = OrderSide.BUY,
    instrument: str = "NSE:RELIANCE",
) -> PlaceOrderCommand:
    return PlaceOrderCommand(
        instrument_id=InstrumentId.parse(instrument),
        side=side,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal(qty)),
        price=Price(value=Decimal(price)),
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
    pos = Position(
        instrument_id=iid,
        quantity=Quantity(value=Decimal(position_qty)),
        avg_price=Price(value=Decimal("2500")),
        realized_pnl=zero,
        unrealized_pnl=zero,
    )
    return RiskContext(
        positions={iid: pos} if Decimal(position_qty) != 0 else {},
        daily_pnl=Decimal(daily_pnl),
        order_count=order_count,
        available_margin=Decimal(available_margin),
    )


# ── RiskManager: approve / reject paths ──────────────────────────────


class TestRiskManagerApproves:
    def test_valid_order_approved(self) -> None:
        mgr = RiskManager(rules=[OrderSizeRule(max_qty=Decimal("100"))])
        result = mgr.check_order(_cmd(qty="10"), _ctx())
        assert result.approved is True
        assert result.reason is None or result.reason == ""


class TestRiskManagerRejectsQuantity:
    def test_rejects_oversized_quantity(self) -> None:
        mgr = RiskManager(rules=[OrderSizeRule(max_qty=Decimal("100"))])
        result = mgr.check_order(_cmd(qty="500"), _ctx())
        assert result.approved is False
        assert result.reason is not None


class TestRiskManagerRejectsNotional:
    def test_rejects_high_notional(self) -> None:
        mgr = RiskManager(rules=[NotionalRule(max_notional=Decimal("100000"))])
        # 2500 * 100 = 250000 > 100000
        result = mgr.check_order(_cmd(qty="100", price="2500"), _ctx())
        assert result.approved is False
        assert result.reason is not None
        assert "notional" in result.reason.lower()


class TestKillSwitch:
    def test_kill_switch_rejects_all_orders(self) -> None:
        mgr = RiskManager(rules=[OrderSizeRule(max_qty=Decimal("10000"))])
        mgr.activate_kill_switch("emergency")
        result = mgr.check_order(_cmd(qty="1"), _ctx())
        assert result.approved is False
        assert "kill" in result.reason.lower()

    def test_kill_switch_reset_allows_orders(self) -> None:
        mgr = RiskManager(rules=[OrderSizeRule(max_qty=Decimal("10000"))])
        mgr.activate_kill_switch("test")
        mgr.reset_kill_switch()
        result = mgr.check_order(_cmd(qty="1"), _ctx())
        assert result.approved is True


class TestDailyLossLimit:
    def test_daily_loss_rejects_when_breached(self) -> None:
        mgr = RiskManager(rules=[DailyLossRule(max_loss=Decimal("50000"))])
        result = mgr.check_order(_cmd(), _ctx(daily_pnl="-50001"))
        assert result.approved is False
        assert "daily loss" in result.reason.lower()

    def test_daily_loss_allows_within_limit(self) -> None:
        mgr = RiskManager(rules=[DailyLossRule(max_loss=Decimal("50000"))])
        result = mgr.check_order(_cmd(), _ctx(daily_pnl="-49999"))
        assert result.approved is True


# ── RiskContext tracks state ──────────────────────────────────────────


class TestRiskContext:
    def test_context_holds_positions(self) -> None:
        ctx = _ctx(position_qty="50")
        assert len(ctx.positions) == 1
        pos = list(ctx.positions.values())[0]
        assert pos.quantity.value == Decimal("50")

    def test_context_holds_pnl(self) -> None:
        ctx = _ctx(daily_pnl="-12345")
        assert ctx.daily_pnl == Decimal("-12345")

    def test_context_holds_order_count(self) -> None:
        ctx = _ctx(order_count=7)
        assert ctx.order_count == 7

    def test_context_holds_margin(self) -> None:
        ctx = _ctx(available_margin="500000")
        assert ctx.available_margin == Decimal("500000")


# ── Fail closed on exception ─────────────────────────────────────────


class TestFailClosed:
    def test_exception_in_rule_rejects(self) -> None:
        class _Boom:
            def check(self, command: object, context: object) -> object:
                raise RuntimeError("boom")

        mgr = RiskManager(rules=[_Boom()])  # type: ignore[list-item]
        result = mgr.check_order(_cmd(), _ctx())
        assert result.approved is False
        assert result.reason is not None
