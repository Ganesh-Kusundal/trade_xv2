"""Integration test: live_actionable gate wiring end-to-end.

Verifies that:
1. BrokerService._ensure_initialized() registers the gate via set_live_actionable_gate()
2. ExecutionManager.buy/sell calls check_live_actionable(self._broker_id)
3. The gate correctly blocks/allows orders based on BrokerService._live_actionable state

This catches regressions where the gate wiring is broken or the ExecutionManager
stops consulting the gate.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from brokers.services._session import (
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


def _make_mock_session() -> MagicMock:
    """Create a minimal mock Session for ExecutionManager."""
    session = MagicMock()
    session.buy.return_value = {"order_id": "TEST-001", "status": "OPEN"}
    session.sell.return_value = {"order_id": "TEST-002", "status": "OPEN"}
    session.orders.return_value = []
    return session


def _make_mock_instrument() -> MagicMock:
    """Create a minimal mock Instrument."""
    inst = MagicMock()
    inst.symbol = "RELIANCE"
    inst.exchange = "NSE"
    return inst


# ── Integration tests ─────────────────────────────────────────────────


class TestGateWiringEndToEnd:
    """Verify the gate is wired from BrokerService through ExecutionManager."""

    def test_gate_blocks_live_broker_buy_when_not_live_actionable(self):
        """ExecutionManager.buy() raises LiveBrokerBlockedError when gate returns False."""
        from brokers.runtime.execution_manager import ExecutionManager

        # Simulate BrokerService wiring the gate to return False
        set_live_actionable_gate(lambda: False)

        em = ExecutionManager(_make_mock_session(), broker_id="dhan")
        with pytest.raises(LiveBrokerBlockedError, match="not live-actionable"):
            em.buy(_make_mock_instrument(), quantity=10, price=Decimal("2500"))

    def test_gate_blocks_live_broker_sell_when_not_live_actionable(self):
        """ExecutionManager.sell() raises LiveBrokerBlockedError when gate returns False."""
        from brokers.runtime.execution_manager import ExecutionManager

        set_live_actionable_gate(lambda: False)

        em = ExecutionManager(_make_mock_session(), broker_id="upstox")
        with pytest.raises(LiveBrokerBlockedError, match="not live-actionable"):
            em.sell(_make_mock_instrument(), quantity=5, price=Decimal("1500"))

    def test_gate_allows_live_broker_buy_when_live_actionable(self):
        """ExecutionManager.buy() proceeds when gate returns True."""
        from brokers.runtime.execution_manager import ExecutionManager

        set_live_actionable_gate(lambda: True)
        session = _make_mock_session()
        em = ExecutionManager(session, broker_id="dhan")

        result = em.buy(_make_mock_instrument(), quantity=10, price=Decimal("2500"))
        assert result == {"order_id": "TEST-001", "status": "OPEN"}
        session.buy.assert_called_once()

    def test_gate_allows_live_broker_sell_when_live_actionable(self):
        """ExecutionManager.sell() proceeds when gate returns True."""
        from brokers.runtime.execution_manager import ExecutionManager

        set_live_actionable_gate(lambda: True)
        session = _make_mock_session()
        em = ExecutionManager(session, broker_id="dhan")

        result = em.sell(_make_mock_instrument(), quantity=5, price=Decimal("1500"))
        assert result == {"order_id": "TEST-002", "status": "OPEN"}
        session.sell.assert_called_once()

    def test_paper_broker_always_allowed(self):
        """ExecutionManager allows paper broker regardless of gate state."""
        from brokers.runtime.execution_manager import ExecutionManager

        set_live_actionable_gate(lambda: False)  # gate is blocking
        session = _make_mock_session()
        em = ExecutionManager(session, broker_id="paper")

        # Should NOT raise - paper is always allowed
        result = em.buy(_make_mock_instrument(), quantity=10, price=Decimal("2500"))
        assert result == {"order_id": "TEST-001", "status": "OPEN"}

    def test_gate_none_blocks_live_broker(self):
        """ExecutionManager blocks live broker when no gate is registered (fail-closed)."""
        from brokers.runtime.execution_manager import ExecutionManager

        # No gate registered - fail-closed default
        em = ExecutionManager(_make_mock_session(), broker_id="dhan")
        with pytest.raises(LiveBrokerBlockedError, match="no live-actionable gate registered"):
            em.buy(_make_mock_instrument(), quantity=10, price=Decimal("2500"))

    def test_broker_service_wires_gate_on_init(self):
        """BrokerService._ensure_initialized() registers the gate."""
        from interface.ui.services.broker_service import BrokerService

        # We need to mock the env path check to avoid real broker bootstrap
        with patch("interface.ui.services.broker_service._ENV_PATH") as mock_env:
            mock_env.exists.return_value = False
            bs = BrokerService()
            bs._ensure_initialized()

        # The gate should now be registered
        # Verify it by checking that check_live_actionable works for paper
        check_live_actionable("paper")  # should not raise

        # And blocks live broker (since _live_actionable defaults to False)
        with pytest.raises(LiveBrokerBlockedError):
            check_live_actionable("dhan")

    def test_gate_reflects_broker_service_state(self):
        """Gate reflects BrokerService._live_actionable state changes."""
        from interface.ui.services.broker_service import BrokerService

        with patch("interface.ui.services.broker_service._ENV_PATH") as mock_env:
            mock_env.exists.return_value = False
            bs = BrokerService()
            bs._ensure_initialized()

        # Initially live_actionable is False
        with pytest.raises(LiveBrokerBlockedError):
            check_live_actionable("dhan")

        # Simulate successful bootstrap
        bs._live_actionable = True

        # Now the gate should allow live orders
        check_live_actionable("dhan")  # should not raise
