"""Tests for the M1 live-actionable gate on Spine B.

The gate ensures that ``brokers.services.orders.place_order`` (and cancel/modify)
cannot reach a live broker unless the production readiness gate has passed.
Paper and mock brokers are always allowed.
"""

from __future__ import annotations

import pytest

from brokers.services._session import (
    LIVE_BROKERS,
    check_live_actionable,
    set_live_actionable_gate,
)
from domain.exceptions import LiveBrokerBlockedError

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_gate():
    """Reset the module-level gate between tests."""
    set_live_actionable_gate(None)
    yield
    set_live_actionable_gate(None)


# ── check_live_actionable unit tests ──────────────────────────────────


class TestCheckLiveActionable:
    """Direct tests on the gate function."""

    def test_paper_always_allowed(self):
        """Paper broker never raises regardless of gate state."""
        check_live_actionable("paper")  # no gate registered — should pass

    def test_mock_always_allowed(self):
        """Any non-live broker is always allowed."""
        check_live_actionable("mock")

    @pytest.mark.parametrize("broker", sorted(LIVE_BROKERS))
    def test_live_broker_blocked_when_no_gate(self, broker: str):
        """Live brokers are blocked when no gate is registered (fail-closed)."""
        with pytest.raises(LiveBrokerBlockedError, match="no live-actionable gate registered"):
            check_live_actionable(broker)

    @pytest.mark.parametrize("broker", sorted(LIVE_BROKERS))
    def test_live_broker_blocked_when_gate_returns_false(self, broker: str):
        """Live brokers are blocked when the gate returns False."""
        set_live_actionable_gate(lambda: False)
        with pytest.raises(LiveBrokerBlockedError, match="not live-actionable"):
            check_live_actionable(broker)

    @pytest.mark.parametrize("broker", sorted(LIVE_BROKERS))
    def test_live_broker_allowed_when_gate_returns_true(self, broker: str):
        """Live brokers pass when the gate returns True."""
        set_live_actionable_gate(lambda: True)
        check_live_actionable(broker)  # should not raise

    def test_gate_exception_propagates(self):
        """If the gate callable raises, the exception propagates."""

        def bad_gate():
            raise OSError("bootstrap failed")

        set_live_actionable_gate(bad_gate)
        with pytest.raises(OSError, match="bootstrap failed"):
            check_live_actionable("dhan")

    def test_case_insensitive_broker(self):
        """Gate works regardless of broker string casing."""
        set_live_actionable_gate(lambda: True)
        check_live_actionable("DHAN")
        check_live_actionable("Dhan")

    def test_set_gate_to_none_restores_fail_closed(self):
        """Setting the gate back to None restores fail-closed behavior."""
        set_live_actionable_gate(lambda: True)
        check_live_actionable("dhan")  # passes

        set_live_actionable_gate(None)
        with pytest.raises(LiveBrokerBlockedError, match="no live-actionable gate registered"):
            check_live_actionable("dhan")


class TestLiveBrokersConstant:
    """Verify the LIVE_BROKERS set is correct."""

    def test_contains_dhan_and_upstox(self):
        assert "dhan" in LIVE_BROKERS
        assert "upstox" in LIVE_BROKERS

    def test_does_not_contain_paper(self):
        assert "paper" not in LIVE_BROKERS

    def test_is_frozen(self):
        assert isinstance(LIVE_BROKERS, frozenset)
