"""Regression tests for R7: extended orders must run the FULL pre-trade risk path.

Previously :class:`ExtendedOrderService` only ran the kill-switch check for
extended (bracket/OTO/cover/slice/super/forever/trigger/GTT) orders and skipped
all other risk limits (daily-loss circuit breaker, margin, concentration,
notional). These tests prove that an extended order which would exceed the
daily-loss limit is REJECTED rather than placed.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from application.oms import PositionManager, RiskConfig, RiskManager
from application.oms._internal.loss_circuit_breaker import LossCircuitBreakerConfig
from application.oms.extended_order_service import ExtendedOrderService


def _make_risk_manager(trip_loss: bool) -> RiskManager:
    """Build a RiskManager whose loss circuit breaker trips easily.

    With ``loss_threshold_pct=0.5`` and a 1,000,000 capital base, a daily PnL of
    -6000 (0.6%) trips the breaker to OPEN, which blocks every order in
    ``check_order``. When ``trip_loss`` is False we record a tiny loss that
    stays below the threshold so orders are allowed through.
    """
    cb_config = LossCircuitBreakerConfig(
        loss_threshold_pct=Decimal("0.5"),
        cooldown_seconds=5,
        window_seconds=10,
    )
    rm = RiskManager(
        position_manager=PositionManager(),
        config=RiskConfig(),
        capital_fn=lambda: Decimal("1000000"),
        loss_cb_config=cb_config,
    )
    if trip_loss:
        rm.update_daily_pnl(Decimal("-6000"))
    else:
        rm.update_daily_pnl(Decimal("-1000"))
    return rm


def _make_service(risk_manager: RiskManager) -> ExtendedOrderService:
    return ExtendedOrderService(
        risk_manager=risk_manager,
        event_bus=MagicMock(),
        broker_service=MagicMock(active_broker_name="upstox"),
    )


def _cover_payload() -> dict:
    return {
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "side": "BUY",
        "quantity": 10,
        "order_type": "MARKET",
        "product_type": "INTRADAY",
        "validity": "DAY",
        "price": "2500",
        "stop_loss_price": "2400",
    }


def _fake_gw() -> MagicMock:
    """A broker gateway whose cover-order call succeeds."""
    gw = MagicMock()
    gw._broker.cover.place_cover_order.return_value = {"status": "success"}
    return gw


# ── Rejection (R7 core) ──────────────────────────────────────────────────────


def test_cover_order_rejected_when_daily_loss_exceeded() -> None:
    """An extended cover order that trips the loss CB must be refused."""
    service = _make_service(_make_risk_manager(trip_loss=True))
    result = service.place_cover_order(_fake_gw(), _cover_payload())

    assert result.success is False
    assert result.risk_rejected is True
    assert "Loss circuit breaker" in (result.error or "")
    # Broker transport must NOT have been reached.
    assert _fake_gw()._broker.cover.place_cover_order.called is False


def test_super_order_rejected_when_daily_loss_exceeded() -> None:
    """Super orders (dhan) also route through the full risk path."""
    service = _make_service(_make_risk_manager(trip_loss=True))
    gw = MagicMock()
    gw.extended.place_super_order.return_value = {"status": "success"}
    payload = {
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "side": "BUY",
        "quantity": 10,
        "order_type": "MARKET",
        "product_type": "INTRADAY",
        "validity": "DAY",
        "price": "2500",
    }
    result = service.place_super_order(gw, payload)

    assert result.success is False
    assert result.risk_rejected is True
    assert "Loss circuit breaker" in (result.error or "")
    assert gw.extended.place_super_order.called is False


def test_slice_order_rejected_when_daily_loss_exceeded() -> None:
    """Slice orders (upstox path) also route through the full risk path."""
    service = _make_service(_make_risk_manager(trip_loss=True))
    gw = MagicMock()
    gw._broker.slice.place_slice_order.return_value = {"status": "success"}
    payload = {
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "side": "BUY",
        "quantity": 10,
        "order_type": "MARKET",
        "product_type": "INTRADAY",
        "validity": "DAY",
        "price": "2500",
    }
    result = service.place_slice_order(gw, payload)

    assert result.success is False
    assert result.risk_rejected is True
    assert "Loss circuit breaker" in (result.error or "")
    assert gw._broker.slice.place_slice_order.called is False


# ── Happy path preserved ─────────────────────────────────────────────────────


def test_cover_order_placed_when_risk_allows() -> None:
    """When the loss CB is below threshold the order proceeds to the broker."""
    service = _make_service(_make_risk_manager(trip_loss=False))
    gw = _fake_gw()
    result = service.place_cover_order(gw, _cover_payload())

    assert result.success is True
    assert result.risk_rejected is False
    assert gw._broker.cover.place_cover_order.called is True


# ── Kill-switch protection still intact ──────────────────────────────────────


def test_kill_switch_still_blocks_extended_orders() -> None:
    """The legacy kill-switch check must remain active alongside risk checks."""
    risk = _make_risk_manager(trip_loss=False)
    risk.set_kill_switch(True)
    service = _make_service(risk)
    gw = _fake_gw()

    result = service.place_cover_order(gw, _cover_payload())

    assert result.success is False
    assert result.risk_rejected is True
    assert "Kill switch" in (result.error or "")
    assert gw._broker.cover.place_cover_order.called is False


# ── Direct unit of the new helper ────────────────────────────────────────────


# ── exit_all is exempt from the kill switch ───────────────────────────────────


def test_exit_all_succeeds_even_when_kill_switch_active() -> None:
    """exit_all only reduces risk (closes positions) and must never be blocked
    by the kill switch — the emergency flatten-all escape hatch must work
    precisely when something has gone wrong badly enough to trip it."""
    risk = _make_risk_manager(trip_loss=False)
    risk.set_kill_switch(True)
    service = _make_service(risk)
    gw = MagicMock()
    gw.extended.exit_all.return_value = {"status": "success"}

    result = service.exit_all(gw)

    assert result.success is True
    assert result.risk_rejected is False
    assert gw.extended.exit_all.called is True


def test_check_risk_helper_returns_none_when_allowed() -> None:
    service = _make_service(_make_risk_manager(trip_loss=False))
    assert service._check_risk(_cover_payload()) is None


def test_check_risk_helper_returns_rejection_result() -> None:
    service = _make_service(_make_risk_manager(trip_loss=True))
    rejection = service._check_risk(_cover_payload())
    assert rejection is not None
    assert rejection.success is False
    assert rejection.risk_rejected is True
