"""RiskManager: oversize reject; kill switch blocks all; fail closed."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from application.risk.context import RiskContext
from application.risk.risk_manager import RiskManager
from application.risk.rules import OrderSizeRule
from domain.commands import PlaceOrderCommand
from domain.enums import OrderSide, OrderType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, Price, Quantity


def _cmd(qty: str = "10") -> PlaceOrderCommand:
    return PlaceOrderCommand(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal(qty)),
        price=Price(value=Decimal("2500")),
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid4()),
    )


def _ctx() -> RiskContext:
    return RiskContext(
        positions={},
        daily_pnl=Decimal("0"),
        order_count=0,
        available_margin=Decimal("1000000"),
    )


def test_reject_oversize_order() -> None:
    mgr = RiskManager(rules=[OrderSizeRule(max_qty=Decimal("100"))])
    result = mgr.check_order(_cmd(qty="500"), _ctx())
    assert not result.approved
    assert result.reason


def test_kill_switch_blocks_all() -> None:
    mgr = RiskManager(rules=[OrderSizeRule(max_qty=Decimal("10000"))])
    mgr.activate_kill_switch("manual test")
    result = mgr.check_order(_cmd(qty="1"), _ctx())
    assert not result.approved
    assert "kill" in result.reason.lower()


def test_kill_switch_reset_allows_orders() -> None:
    mgr = RiskManager(rules=[OrderSizeRule(max_qty=Decimal("10000"))])
    mgr.activate_kill_switch("test")
    mgr.reset_kill_switch()
    result = mgr.check_order(_cmd(qty="1"), _ctx())
    assert result.approved


def test_exception_fail_closed() -> None:
    class _Boom:
        def check(self, command: object, context: object) -> object:
            raise RuntimeError("boom")

    mgr = RiskManager(rules=[_Boom()])  # type: ignore[list-item]
    result = mgr.check_order(_cmd(), _ctx())
    assert not result.approved
    assert result.reason
