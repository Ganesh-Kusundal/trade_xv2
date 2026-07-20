"""Shared assertion helpers for OMS and risk tests."""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.oms._internal.risk_manager import RiskManager
    from domain import Order


def assert_order_allowed(rm: RiskManager, order: Order) -> None:
    """Assert that the risk manager allows the order."""
    result = rm.check_order(order)
    assert result.allowed is True, f"Expected order to be allowed, got rejected: {result.reason}"


def assert_order_rejected(rm: RiskManager, order: Order, reason_fragment: str = "") -> None:
    """Assert that the risk manager rejects the order.
    
    Args:
        reason_fragment: Optional substring that should appear in the rejection reason.
    """
    result = rm.check_order(order)
    assert result.allowed is False, f"Expected order to be rejected, but it was allowed"
    if reason_fragment:
        assert reason_fragment.lower() in (result.reason or "").lower(), (
            f"Expected reason to contain '{reason_fragment}', got: {result.reason}"
        )


def assert_order_state(order_manager, order_id: str, *, filled_qty: int, status: str) -> None:
    """Assert specific order state after operations."""
    order = order_manager.get_order(order_id)
    assert order is not None, f"Order {order_id} not found"
    assert int(order.filled_quantity) == filled_qty, (
        f"Expected filled_quantity={filled_qty}, got {order.filled_quantity}"
    )
    assert order.status.value == status, (
        f"Expected status={status}, got {order.status}"
    )


def assert_trade_count(trade_repository, expected: int) -> None:
    """Assert the number of recorded trades."""
    trades = trade_repository.get_all() if hasattr(trade_repository, 'get_all') else []
    assert len(trades) == expected, f"Expected {expected} trades, got {len(trades)}"
