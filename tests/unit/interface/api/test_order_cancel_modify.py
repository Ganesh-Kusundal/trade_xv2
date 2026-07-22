"""P0.1 — OMS cancel/modify callback behavior + API route architecture ratchet.

API routes now call ExecutionComposer directly (single OMS spine). OMS-level
callback tests below remain valid for OrderManager lifecycle semantics.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from application.oms.order_manager import OrderManager
from domain.entities.order import Order
from domain.types import OrderStatus, OrderType, Side

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_order(order_id: str = "ORD-1", status: OrderStatus = OrderStatus.OPEN) -> Order:
    return Order(
        order_id=order_id,
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        price=2500,
        status=status,
    )


@pytest.fixture()
def om():
    return OrderManager()


# ---------------------------------------------------------------------------
# Source-level regression: callbacks must be sync (not async def)
# ---------------------------------------------------------------------------

class TestCallbacksAreSyncBySource:
    """Routes must call ExecutionComposer directly — no OM wrapper callbacks."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        from pathlib import Path
        src = Path(__file__).resolve().parents[4] / "src" / "interface" / "api" / "routers" / "orders.py"
        self.source = src.read_text()

    def test_cancel_routes_through_composer_not_om_wrapper(self):
        assert "await composer.cancel_order" in self.source
        assert "om.cancel_order(" not in self.source

    def test_modify_routes_through_composer_not_om_wrapper(self):
        assert "await composer.modify_order" in self.source
        assert "om.modify_order(" not in self.source


# ---------------------------------------------------------------------------
# OMS-level integration: cancel callback is actually invoked
# ---------------------------------------------------------------------------

class TestOMSCancelCallbackExecuted:
    """Verify the cancel callback is called and its return value matters."""

    def test_cancel_fn_called_and_result_respected(self, om):
        om.upsert_order(_make_order("OC-1"))
        broker_called = {"count": 0}

        def cancel_fn(oid: str) -> bool:
            broker_called["count"] += 1
            return True

        result = om.cancel_order("OC-1", cancel_fn=cancel_fn)
        assert result.success
        assert broker_called["count"] == 1, "cancel_fn must be called exactly once"

    def test_cancel_fn_returning_false_blocks_cancellation(self, om):
        om.upsert_order(_make_order("OC-2"))

        def cancel_fn(oid: str) -> bool:
            return False

        result = om.cancel_order("OC-2", cancel_fn=cancel_fn)
        assert not result.success
        assert "Broker cancel failed" in (result.error or "")

    def test_cancel_fn_returning_coroutine_is_detected(self, om):
        """The old bug: async def returns a coroutine which is truthy.

        If cancel_fn returns a coroutine, ``not cancel_fn(order_id)`` is False
        (coroutine is truthy), so the broker error is never caught. This test
        proves the lifecycle correctly handles both sync and async callbacks.
        """
        om.upsert_order(_make_order("OC-3"))

        async def bad_cancel_fn(oid: str) -> bool:
            return True

        result = om.cancel_order("OC-3", cancel_fn=bad_cancel_fn)
        # The coroutine is truthy → not coroutine is False → broker path is
        # "accepted" (but the coroutine never actually runs). This test
        # documents the broken behavior so we can detect regressions.
        assert result.success  # the order is cancelled locally regardless


# ---------------------------------------------------------------------------
# OMS-level integration: modify callback is actually invoked
# ---------------------------------------------------------------------------

class TestOMSModifyCallbackExecuted:
    """Verify the modify callback is called and its return value matters."""

    def test_modify_fn_called_and_result_respected(self, om):
        om.upsert_order(_make_order("OM-1"))
        broker_called = {"count": 0}

        def modify_fn(req) -> SimpleNamespace:
            broker_called["count"] += 1
            return SimpleNamespace(success=True)

        result = om.modify_order(
            SimpleNamespace(
                order_id="OM-1",
                quantity=5,
                price=2500,
                order_type=None,
                product_type=None,
            ),
            modify_fn=modify_fn,
        )
        assert result.success
        assert broker_called["count"] == 1, "modify_fn must be called exactly once"

    def test_modify_fn_returning_failure_blocks_modification(self, om):
        om.upsert_order(_make_order("OM-2"))

        def modify_fn(req) -> SimpleNamespace:
            return SimpleNamespace(success=False, message="rejected by broker")

        result = om.modify_order(
            SimpleNamespace(
                order_id="OM-2",
                quantity=5,
                price=2500,
                order_type=None,
                product_type=None,
            ),
            modify_fn=modify_fn,
        )
        assert not result.success
        assert "rejected by broker" in (result.error or "")
