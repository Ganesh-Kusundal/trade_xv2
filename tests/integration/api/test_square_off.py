"""Tests for square-off service — verify OMS risk integration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.oms.square_off_service import (
    SquareOffRejectedError,
    SquareOffService,
)

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_position(symbol: str = "RELIANCE", quantity: int = 10, product_type: str = "INTRADAY"):
    pos = MagicMock()
    pos.symbol = symbol
    pos.exchange = "NSE"
    pos.quantity = quantity
    pos.product_type = MagicMock(value=product_type)
    return pos


def _make_order_manager(reject: bool = False):
    om = MagicMock()
    if reject:
        result = MagicMock()
        result.success = False
        result.error = "Risk rejected"
        om.place_order.return_value = result
    else:
        result = MagicMock()
        result.success = True
        result.order = MagicMock()
        result.order.order_id = "O-123"
        om.place_order.return_value = result
    return om


def _make_position_manager(positions=None):
    pm = MagicMock()
    pm.get_positions.return_value = positions or []
    return pm


def _make_risk_manager(kill_switch_active: bool = False):
    rm = MagicMock()
    rm.is_kill_switch_active.return_value = kill_switch_active
    return rm


def _make_event_bus():
    return MagicMock()


def _make_service(
    positions=None,
    kill_switch_active: bool = False,
    reject_orders: bool = False,
) -> SquareOffService:
    return SquareOffService(
        order_manager=_make_order_manager(reject=reject_orders),
        position_manager=_make_position_manager(positions),
        risk_manager=_make_risk_manager(kill_switch_active),
        event_bus=_make_event_bus(),
    )


# ── Kill Switch Tests ───────────────────────────────────────────────────


class TestKillSwitchBlocksSquareOff:
    def test_square_off_rejected_when_kill_switch_active(self):
        positions = [_make_position("RELIANCE", 10)]
        svc = _make_service(positions=positions, kill_switch_active=True)

        with pytest.raises(SquareOffRejectedError, match="Kill switch"):
            svc.square_off()

    def test_square_off_allowed_when_kill_switch_inactive(self):
        positions = [_make_position("RELIANCE", 10)]
        svc = _make_service(positions=positions, kill_switch_active=False)

        summary = svc.square_off()
        assert summary.status == "completed"


# ── Position Filtering Tests ────────────────────────────────────────────


class TestPositionFiltering:
    def test_no_positions_returns_no_positions(self):
        svc = _make_service(positions=[])
        summary = svc.square_off()
        assert summary.status == "no_positions"
        assert summary.squared_off == 0

    def test_filters_to_specific_symbol(self):
        positions = [
            _make_position("RELIANCE", 10),
            _make_position("TCS", 5),
        ]
        svc = _make_service(positions=positions)
        summary = svc.square_off(symbol="RELIANCE")
        assert summary.squared_off == 1

    def test_only_non_zero_positions(self):
        positions = [
            _make_position("RELIANCE", 10),
            _make_position("TCS", 0),
        ]
        svc = _make_service(positions=positions)
        summary = svc.square_off()
        assert summary.squared_off == 1


# ── Product Type Tests ──────────────────────────────────────────────────


class TestProductTypePreservation:
    def test_preserves_position_product_type(self):
        """Verify delivery positions are not squared off as INTRADAY."""
        pos = _make_position("RELIANCE", 10)
        pos.product_type = MagicMock(value="DELIVERY")
        svc = _make_service(positions=[pos])

        svc.square_off()

        # Verify the OMS was called with the correct product type
        call_args = svc._oms.place_order.call_args
        cmd = call_args[0][0]
        assert cmd.product_type.value == "DELIVERY"

    def test_defaults_to_intraday_when_product_type_missing(self):
        pos = _make_position("RELIANCE", 10)
        pos.product_type = None
        svc = _make_service(positions=[pos])

        svc.square_off()

        call_args = svc._oms.place_order.call_args
        cmd = call_args[0][0]
        assert cmd.product_type.value == "INTRADAY"


# ── Risk Manager Integration Tests ──────────────────────────────────────


class TestRiskManagerIntegration:
    def test_each_order_goes_through_oms(self):
        positions = [
            _make_position("RELIANCE", 10),
            _make_position("TCS", 5),
        ]
        svc = _make_service(positions=positions)

        svc.square_off()

        # OMS should be called once per position
        assert svc._oms.place_order.call_count == 2

    def test_rejected_orders_recorded_in_summary(self):
        positions = [_make_position("RELIANCE", 10)]
        svc = _make_service(positions=positions, reject_orders=True)

        summary = svc.square_off()
        assert summary.failed == 1
        assert summary.squared_off == 0


# ── Event Publishing Tests ──────────────────────────────────────────────


class TestEventPublishing:
    def test_publishes_aggregate_event(self):
        positions = [_make_position("RELIANCE", 10)]
        svc = _make_service(positions=positions)

        svc.square_off()

        svc._events.publish.assert_called_once()
        event = svc._events.publish.call_args[0][0]
        assert event.event_type == "ORDER_PLACED"
        assert "square_off" in event.payload.get("order_type", "")

    def test_no_event_when_no_positions(self):
        svc = _make_service(positions=[])
        svc.square_off()
        svc._events.publish.assert_not_called()


# ── Correlation ID Tests ────────────────────────────────────────────────


class TestCorrelationId:
    def test_unique_correlation_ids_per_order(self):
        positions = [
            _make_position("RELIANCE", 10),
            _make_position("TCS", 5),
        ]
        svc = _make_service(positions=positions)

        svc.square_off()

        calls = svc._oms.place_order.call_args_list
        ids = [call[0][0].correlation_id for call in calls]
        assert len(ids) == len(set(ids))  # All unique
        assert all(id.startswith("so-") for id in ids)
