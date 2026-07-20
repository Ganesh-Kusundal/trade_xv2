"""Tests for the single live-order authority gate (P1-T1, drift D2).

Verifies the fail-closed authorization path that every order-placing surface
(normal, super/forever/exit-all, API, CLI) must pass before reaching a broker
executor:

1. paper/mock brokers are always allowed;
2. live brokers are blocked when ``allow_live_orders`` is off;
3. live brokers are blocked when no live-actionable gate is registered;
4. a payload that cannot be modelled into a domain ``Order`` is REJECTED,
   never silently allowed (the D2 ``_check_risk`` silent-skip bug).
"""

from __future__ import annotations

import pytest

from application.oms.live_order_authority import RiskRejectedError, authorize_live_order
from brokers.services._session import LiveBrokerBlockedError


def test_paper_broker_always_allowed() -> None:
    # paper never hits the live gate — returns without raising
    authorize_live_order(broker="paper", allow_live_orders=False, risk_manager=None)


def test_live_blocked_when_flag_off() -> None:
    with pytest.raises(LiveBrokerBlockedError):
        authorize_live_order(
            broker="dhan",
            allow_live_orders=False,
            risk_manager=None,
            live_actionable=lambda: True,
        )


def test_live_blocked_when_gate_unset() -> None:
    with pytest.raises(LiveBrokerBlockedError):
        authorize_live_order(
            broker="dhan",
            allow_live_orders=True,
            risk_manager=None,
            live_actionable=None,
        )


def test_live_allowed_when_flag_on_and_gate_true_no_risk() -> None:
    # gate open, flag on, no risk manager wired -> allowed
    authorize_live_order(
        broker="dhan",
        allow_live_orders=True,
        risk_manager=None,
        live_actionable=lambda: True,
    )


def test_risk_rejects_malformed_payload() -> None:
    # coercion failure must REJECT, not skip (fixes D2 _check_risk bug)
    class _RM:
        def is_kill_switch_active(self) -> bool:
            return False

        def check_order(self, order: object) -> object:  # pragma: no cover - must not run
            raise AssertionError("check_order must not be reached for an unbuildable payload")

    with pytest.raises(RiskRejectedError):
        authorize_live_order(
            broker="dhan",
            allow_live_orders=True,
            risk_manager=_RM(),
            live_actionable=lambda: True,
            risk_payload={"side": "NOT_A_SIDE"},  # invalid enum -> unbuildable
        )


def test_kill_switch_blocks() -> None:
    class _RM:
        def is_kill_switch_active(self) -> bool:
            return True

    with pytest.raises(RiskRejectedError):
        authorize_live_order(
            broker="dhan",
            allow_live_orders=True,
            risk_manager=_RM(),
            live_actionable=lambda: True,
        )


def test_risk_rejection_propagates() -> None:
    class _Result:
        allowed = False
        reason = "notional limit exceeded"

    class _RM:
        def is_kill_switch_active(self) -> bool:
            return False

        def check_order(self, order: object) -> _Result:
            return _Result()

    with pytest.raises(RiskRejectedError):
        authorize_live_order(
            broker="dhan",
            allow_live_orders=True,
            risk_manager=_RM(),
            live_actionable=lambda: True,
            risk_payload={"symbol": "RELIANCE", "side": "BUY", "quantity": 1},
        )


def test_valid_order_passes_risk() -> None:
    class _Result:
        allowed = True
        reason = None

    class _RM:
        def is_kill_switch_active(self) -> bool:
            return False

        def check_order(self, order: object) -> _Result:
            return _Result()

    # gate open, flag on, valid payload, risk allows -> no raise
    authorize_live_order(
        broker="dhan",
        allow_live_orders=True,
        risk_manager=_RM(),
        live_actionable=lambda: True,
        risk_payload={"symbol": "RELIANCE", "side": "BUY", "quantity": 1},
    )
