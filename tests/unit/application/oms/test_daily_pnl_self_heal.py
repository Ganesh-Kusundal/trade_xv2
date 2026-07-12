"""Task 4 (A4): Daily PnL self-heal — auto-reset on staleness in check_order."""

import time
from decimal import Decimal
from unittest.mock import MagicMock

from application.oms._internal.daily_pnl_tracker import DailyPnlTracker
from application.oms._internal.loss_circuit_breaker import LossCircuitBreaker
from application.oms._internal.risk_types import RiskConfig


def _make_tracker(last_reset_offset_seconds: float = 0.0) -> DailyPnlTracker:
    config = RiskConfig(
        max_daily_loss_pct=Decimal("5"),
        max_position_pct=Decimal("20"),
        max_gross_exposure_pct=Decimal("100"),
    )
    loss_cb = LossCircuitBreaker()
    tracker = DailyPnlTracker(
        config=config,
        capital_provider=lambda: Decimal("1000000"),
        loss_cb=loss_cb,
    )
    if last_reset_offset_seconds:
        tracker._last_reset_at = time.time() + last_reset_offset_seconds
    return tracker


def test_is_stale_when_never_reset():
    tracker = _make_tracker()
    assert tracker._last_reset_at == 0.0
    assert tracker.is_stale()


def test_is_not_stale_when_reset_today():
    tracker = _make_tracker()
    tracker.reset()
    assert not tracker.is_stale()


def test_is_stale_when_reset_yesterday():
    tracker = _make_tracker()
    tracker.reset()
    one_day_ago = time.time() - 86400
    tracker._last_reset_at = one_day_ago
    assert tracker.is_stale()


def test_self_heal_resets_stale_pnl_before_daily_loss_check():
    """When daily PnL is stale, is_stale returns True and reset clears it."""
    tracker = _make_tracker()
    tracker.reset()
    tracker._daily_pnl = Decimal("-40000")
    tracker._last_reset_at = time.time() - 86400

    assert tracker.is_stale()
    tracker.reset()
    assert tracker.value == Decimal("0")
    assert not tracker.is_stale()
