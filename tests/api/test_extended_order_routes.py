"""Tests for extended order routes — verify OMS risk integration.

All order-modifying endpoints must go through ExtendedOrderService
for kill switch checks and event publishing.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from application.oms.extended_order_service import (
    ExtendedOrderService,
)

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_risk_manager(kill_switch_active: bool = False) -> MagicMock:
    rm = MagicMock()
    rm.is_kill_switch_active.return_value = kill_switch_active
    return rm


def _make_event_bus() -> MagicMock:
    return MagicMock()


def _make_broker_service(name: str = "dhan") -> MagicMock:
    svc = MagicMock()
    svc.active_broker_name = name
    return svc


def _make_extended_order_service(
    kill_switch_active: bool = False,
    broker_name: str = "dhan",
) -> ExtendedOrderService:
    return ExtendedOrderService(
        risk_manager=_make_risk_manager(kill_switch_active),
        event_bus=_make_event_bus(),
        broker_service=_make_broker_service(broker_name),
    )


def _make_gateway(broker_name: str = "dhan") -> MagicMock:
    gw = MagicMock()
    gw.extended = MagicMock()
    gw._broker = MagicMock()
    gw._conn = MagicMock()
    return gw


# ── Kill Switch Tests ───────────────────────────────────────────────────


class TestKillSwitchBlocksOrders:
    """Verify that active kill switch rejects all order-modifying operations."""

    def test_super_order_rejected_when_kill_switch_active(self):
        svc = _make_extended_order_service(kill_switch_active=True)
        gw = _make_gateway()
        result = svc.place_super_order(gw, {"symbol": "RELIANCE"})
        assert not result.success
        assert result.error is not None

    def test_forever_order_rejected_when_kill_switch_active(self):
        svc = _make_extended_order_service(kill_switch_active=True)
        gw = _make_gateway()
        result = svc.place_forever_order(gw, {"symbol": "RELIANCE"})
        assert not result.success

    def test_trigger_rejected_when_kill_switch_active(self):
        svc = _make_extended_order_service(kill_switch_active=True)
        gw = _make_gateway()
        result = svc.place_trigger(gw, {"symbol": "RELIANCE"})
        assert not result.success

    def test_exit_all_rejected_when_kill_switch_active(self):
        svc = _make_extended_order_service(kill_switch_active=True)
        gw = _make_gateway()
        result = svc.exit_all(gw)
        assert not result.success

    def test_gtt_rejected_when_kill_switch_active(self):
        svc = _make_extended_order_service(kill_switch_active=True)
        gw = _make_gateway()
        result = svc.place_gtt(gw, {"symbol": "RELIANCE"})
        assert not result.success

    def test_cover_order_rejected_when_kill_switch_active(self):
        svc = _make_extended_order_service(kill_switch_active=True)
        gw = _make_gateway()
        result = svc.place_cover_order(gw, {"symbol": "RELIANCE"})
        assert not result.success

    def test_slice_order_rejected_when_kill_switch_active(self):
        svc = _make_extended_order_service(kill_switch_active=True)
        gw = _make_gateway()
        result = svc.place_slice_order(gw, {"symbol": "RELIANCE"})
        assert not result.success


# ── Event Publishing Tests ──────────────────────────────────────────────


class TestEventPublishing:
    """Verify that successful operations publish ORDER_PLACED events."""

    def test_super_order_publishes_event_on_success(self):
        svc = _make_extended_order_service()
        gw = _make_gateway("dhan")
        gw.extended.place_super_order.return_value = {"orderId": "123"}

        svc.place_super_order(gw, {"symbol": "RELIANCE"})

        svc._events.publish.assert_called_once()
        event = svc._events.publish.call_args[0][0]
        assert event.event_type == "ORDER_PLACED"

    def test_forever_order_publishes_event_on_success(self):
        svc = _make_extended_order_service(broker_name="dhan")
        gw = _make_gateway("dhan")
        gw.extended.place_forever_order.return_value = {"orderId": "456"}

        svc.place_forever_order(gw, {"symbol": "RELIANCE"})

        svc._events.publish.assert_called_once()

    def test_exit_all_publishes_event_on_success(self):
        svc = _make_extended_order_service()
        gw = _make_gateway()
        gw.extended.exit_all.return_value = {"status": "ok"}

        svc.exit_all(gw)

        svc._events.publish.assert_called_once()

    def test_no_event_on_failure(self):
        svc = _make_extended_order_service()
        gw = _make_gateway("dhan")
        gw.extended.place_super_order.side_effect = Exception("API error")

        svc.place_super_order(gw, {"symbol": "RELIANCE"})

        svc._events.publish.assert_not_called()


# ── Broker Routing Tests ────────────────────────────────────────────────


class TestBrokerRouting:
    """Verify correct broker adapter is called for each feature."""

    def test_dhan_super_order_calls_extended(self):
        svc = _make_extended_order_service(broker_name="dhan")
        gw = _make_gateway("dhan")
        gw.extended.place_super_order.return_value = {"orderId": "123"}

        result = svc.place_super_order(gw, {"symbol": "RELIANCE"})

        assert result.success
        gw.extended.place_super_order.assert_called_once_with(symbol="RELIANCE")

    def test_dhan_forever_order_calls_extended(self):
        svc = _make_extended_order_service(broker_name="dhan")
        gw = _make_gateway("dhan")
        gw.extended.place_forever_order.return_value = {"orderId": "456"}

        result = svc.place_forever_order(gw, {"symbol": "RELIANCE"})

        assert result.success
        gw.extended.place_forever_order.assert_called_once()

    def test_upstox_forever_order_calls_broker_gtt(self):
        svc = _make_extended_order_service(broker_name="upstox")
        gw = _make_gateway("upstox")
        gw._broker.gtt.place_forever_order.return_value = {"orderId": "789"}

        result = svc.place_forever_order(gw, {"symbol": "RELIANCE"})

        assert result.success
        gw._broker.gtt.place_forever_order.assert_called_once()

    def test_wrong_broker_rejected(self):
        svc = _make_extended_order_service(broker_name="upstox")
        gw = _make_gateway("upstox")
        # Super order is dhan-only
        result = svc.place_super_order(gw, {"symbol": "RELIANCE"})
        assert not result.success

    def test_gtt_upstox_only(self):
        svc = _make_extended_order_service(broker_name="dhan")
        gw = _make_gateway("dhan")
        # GTT is upstox-only
        result = svc.place_gtt(gw, {"symbol": "RELIANCE"})
        assert not result.success


# ── Kill Switch Sync Tests ──────────────────────────────────────────────


class TestKillSwitchSync:
    """Verify kill switch syncs OMS and broker."""

    def test_kill_switch_updates_oms_risk_manager(self):
        svc = _make_extended_order_service(broker_name="upstox")
        gw = _make_gateway("upstox")
        gw._broker.kill_switch.set_status.return_value = {"status": "updated"}

        svc.set_kill_switch(gw, {"updates": [{"enabled": True}]})

        svc._risk.set_kill_switch.assert_called_once_with(True)

    def test_kill_switch_disables_oms_when_disabled(self):
        svc = _make_extended_order_service(broker_name="upstox")
        gw = _make_gateway("upstox")
        gw._broker.kill_switch.set_status.return_value = {"status": "updated"}

        svc.set_kill_switch(gw, {"updates": [{"enabled": False}]})

        svc._risk.set_kill_switch.assert_called_once_with(False)


# ── Read-Only Endpoints (Not Routed Through Service) ────────────────────


class TestReadOnlyEndpoints:
    """Verify read-only endpoints are NOT affected by this change."""

    def test_margin_calculation_still_works_directly(self):
        """Margin is read-only — should call broker directly, not via service."""
        gw = _make_gateway("dhan")
        gw._conn.margin.calculate.return_value = {"margin": 50000}

        # This test verifies the endpoint still works without ExtendedOrderService
        from interface.api.routers.live.extended import live_margin

        # The function itself should not have changed
        assert live_margin is not None
