"""Tests for post-restart reconciliation order placement gate."""

from __future__ import annotations

from decimal import Decimal

from application.oms.context import TradingContext
from application.oms.order_manager import OmsOrderCommand
from domain import OrderType, ProductType, Side


class _FakeReconciler:
    def reconcile(self, local_orders, local_positions):
        return type("Report", (), {"has_drift": False, "drift_items": []})()


def test_orders_blocked_until_reconciliation_completes() -> None:
    tc = TradingContext(
        replay_events=False,
        enable_durable_orders=False,
        reconciliation_service=_FakeReconciler(),
        reconciliation_interval_seconds=3600,
    )
    assert not tc.health()["reconciliation_ready"]

    cmd = OmsOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        price=Decimal("0"),
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        correlation_id="test:recon-gate:1",
    )
    blocked = tc.order_manager.place_order(cmd, submit_fn=lambda c: None)
    assert not blocked.success
    assert "reconciliation" in (blocked.error or "").lower()


def test_orders_allowed_after_startup_reconciliation() -> None:
    tc = TradingContext(
        replay_events=False,
        enable_durable_orders=False,
        reconciliation_service=_FakeReconciler(),
        reconciliation_interval_seconds=3600,
    )
    assert tc._reconciliation_service is not None
    tc._reconciliation_service.run_now()
    assert tc.health()["reconciliation_ready"]

    cmd = OmsOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        price=Decimal("0"),
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        correlation_id="test:recon-gate:2",
    )

    def _submit(command):
        from datetime import datetime, timezone
        from domain.entities import Order, OrderStatus

        return Order(
            order_id="broker-1",
            symbol=command.symbol,
            exchange=command.exchange,
            side=command.side,
            order_type=command.order_type,
            quantity=command.quantity,
            product_type=command.product_type,
            status=OrderStatus.OPEN,
            timestamp=datetime.now(timezone.utc),
            correlation_id=command.correlation_id,
        )

    result = tc.order_manager.place_order(cmd, submit_fn=_submit)
    assert result.success
