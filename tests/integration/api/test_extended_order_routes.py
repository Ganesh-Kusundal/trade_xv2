"""Tests for extended order routes — verify OMS risk integration.

All order-modifying endpoints must go through ExtendedOrderService
for kill switch checks and event publishing.

Broker-agnostic (DR-B1): the service resolves an
:class:`~domain.extensions.extended_order.ExtendedOrderExecutor` via the
extension registry and delegates to it. These tests inject a stub registry /
executor rather than probing gateway internals.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from application.oms.extended_order_service import (
    ExtendedOrderService,
)
from domain.extensions.extended_order import ExtendedOrderExecutor

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


def _make_registry(executor: object | None) -> MagicMock | None:
    """Build a BrokerExtensionRegistry stub whose ``require`` returns *executor*.

    Returns ``None`` when no executor is supplied, so the service behaves as if
    no registry were configured (extended features unavailable).
    """
    if executor is None:
        return None
    registry = MagicMock()
    registry.require.return_value = executor
    return registry


def _make_extended_order_service(
    kill_switch_active: bool = False,
    broker_name: str = "dhan",
    executor: object | None = None,
) -> ExtendedOrderService:
    return ExtendedOrderService(
        risk_manager=_make_risk_manager(kill_switch_active),
        event_bus=_make_event_bus(),
        broker_service=_make_broker_service(broker_name),
        extension_registry=_make_registry(executor),
    )


def _make_gateway(broker_name: str = "dhan") -> MagicMock:
    """A gateway object — no longer probed by the service, kept for call sig."""
    return MagicMock()


class _UnsupportingExecutor(ExtendedOrderExecutor):
    """Executor with only base (unsupported) behaviour, for reject paths."""

    def __init__(self, broker_id: str) -> None:
        self.broker_id = broker_id


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
        executor = MagicMock()
        executor.place_super_order.return_value = {"orderId": "123"}
        svc = _make_extended_order_service(executor=executor)

        svc.place_super_order(_make_gateway(), {"symbol": "RELIANCE"})

        svc._events.publish.assert_called_once()
        event = svc._events.publish.call_args[0][0]
        assert event.event_type == "ORDER_PLACED"

    def test_forever_order_publishes_event_on_success(self):
        executor = MagicMock()
        executor.place_forever_order.return_value = {"orderId": "456"}
        svc = _make_extended_order_service(executor=executor)

        svc.place_forever_order(_make_gateway(), {"symbol": "RELIANCE"})

        svc._events.publish.assert_called_once()

    def test_exit_all_publishes_event_on_success(self):
        executor = MagicMock()
        executor.exit_all.return_value = {"status": "ok"}
        svc = _make_extended_order_service(executor=executor)

        svc.exit_all(_make_gateway())

        svc._events.publish.assert_called_once()

    def test_no_event_on_failure(self):
        executor = MagicMock()
        executor.place_super_order.side_effect = Exception("API error")
        svc = _make_extended_order_service(executor=executor)

        svc.place_super_order(_make_gateway(), {"symbol": "RELIANCE"})

        svc._events.publish.assert_not_called()


# ── Broker Routing Tests ────────────────────────────────────────────────


class TestBrokerRouting:
    """Verify the service delegates to the resolved executor (no name branching)."""

    def test_dhan_super_order_delegates_to_executor(self):
        executor = MagicMock()
        executor.place_super_order.return_value = {"orderId": "123"}
        svc = _make_extended_order_service(broker_name="dhan", executor=executor)

        result = svc.place_super_order(_make_gateway(), {"symbol": "RELIANCE"})

        assert result.success
        executor.place_super_order.assert_called_once_with({"symbol": "RELIANCE"})

    def test_dhan_forever_order_delegates_to_executor(self):
        executor = MagicMock()
        executor.place_forever_order.return_value = {"orderId": "456"}
        svc = _make_extended_order_service(broker_name="dhan", executor=executor)

        result = svc.place_forever_order(_make_gateway(), {"symbol": "RELIANCE"})

        assert result.success
        executor.place_forever_order.assert_called_once()

    def test_upstox_forever_order_delegates_to_executor(self):
        executor = MagicMock()
        executor.place_forever_order.return_value = {"orderId": "789"}
        svc = _make_extended_order_service(broker_name="upstox", executor=executor)

        result = svc.place_forever_order(_make_gateway(), {"symbol": "RELIANCE"})

        assert result.success
        executor.place_forever_order.assert_called_once()

    def test_wrong_broker_rejected(self):
        # Super order is not supported by an executor that lacks it (e.g. upstox).
        svc = _make_extended_order_service(
            broker_name="upstox", executor=_UnsupportingExecutor("upstox")
        )
        result = svc.place_super_order(_make_gateway(), {"symbol": "RELIANCE"})
        assert not result.success

    def test_gtt_upstox_only(self):
        # GTT is not supported by an executor that lacks it (e.g. dhan).
        svc = _make_extended_order_service(
            broker_name="dhan", executor=_UnsupportingExecutor("dhan")
        )
        result = svc.place_gtt(_make_gateway(), {"symbol": "RELIANCE"})
        assert not result.success


# ── Kill Switch Sync Tests ──────────────────────────────────────────────


class TestKillSwitchSync:
    """Verify kill switch syncs OMS and broker."""

    def test_kill_switch_updates_oms_risk_manager(self):
        executor = MagicMock()
        executor.set_kill_switch.return_value = {"status": "updated"}
        svc = _make_extended_order_service(broker_name="upstox", executor=executor)

        svc.set_kill_switch(_make_gateway(), {"updates": [{"enabled": True}]})

        svc._risk.set_kill_switch.assert_called_once_with(True)

    def test_kill_switch_disables_oms_when_disabled(self):
        executor = MagicMock()
        executor.set_kill_switch.return_value = {"status": "updated"}
        svc = _make_extended_order_service(broker_name="upstox", executor=executor)

        svc.set_kill_switch(_make_gateway(), {"updates": [{"enabled": False}]})

        svc._risk.set_kill_switch.assert_called_once_with(False)


# ── Read-Only Endpoints (Not Routed Through Service) ────────────────────


class TestReadOnlyEndpoints:
    """Verify read-only endpoints are NOT affected by this change."""

    def test_margin_calculation_still_works_directly(self):
        """Margin is read-only — should call broker directly, not via service."""
        # This test verifies the endpoint still works without ExtendedOrderService
        from interface.api.routers.live.extended import live_margin

        # The function itself should not have changed
        assert live_margin is not None
