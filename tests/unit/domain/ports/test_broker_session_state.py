"""Unit tests for unified broker session FSM."""

from __future__ import annotations

import pytest

from domain.ports.broker_session_state import (
    BrokerSessionState,
    InvalidSessionTransitionError,
    assert_valid_transition,
    build_session_status,
    transition_state,
)
from domain.session_status import PHASE_READY_MARKET, SessionStatus


@pytest.mark.unit
@pytest.mark.parametrize(
    ("current", "target"),
    [
        (BrokerSessionState.CREATED, BrokerSessionState.INITIALIZING),
        (BrokerSessionState.INITIALIZING, BrokerSessionState.AUTHENTICATING),
        (BrokerSessionState.AUTHENTICATING, BrokerSessionState.CONNECTED),
        (BrokerSessionState.CONNECTED, BrokerSessionState.HEALTHY),
        (BrokerSessionState.HEALTHY, BrokerSessionState.DEGRADED),
        (BrokerSessionState.DEGRADED, BrokerSessionState.RECOVERING),
        (BrokerSessionState.RECOVERING, BrokerSessionState.HEALTHY),
        (BrokerSessionState.HEALTHY, BrokerSessionState.DISCONNECTED),
        (BrokerSessionState.DISCONNECTED, BrokerSessionState.RECOVERING),
        (BrokerSessionState.HEALTHY, BrokerSessionState.SHUTDOWN),
    ],
)
def test_valid_transitions(current: BrokerSessionState, target: BrokerSessionState) -> None:
    assert transition_state(current, target) == target


@pytest.mark.unit
@pytest.mark.parametrize(
    ("current", "target"),
    [
        (BrokerSessionState.SHUTDOWN, BrokerSessionState.HEALTHY),
        (BrokerSessionState.CREATED, BrokerSessionState.HEALTHY),
        (BrokerSessionState.DISCONNECTED, BrokerSessionState.HEALTHY),
    ],
)
def test_invalid_transitions(current: BrokerSessionState, target: BrokerSessionState) -> None:
    with pytest.raises(InvalidSessionTransitionError):
        assert_valid_transition(current, target)


@pytest.mark.unit
def test_build_session_status_from_connect_snapshot() -> None:
    connect = SessionStatus(
        phase=PHASE_READY_MARKET,
        broker_id="paper",
        mode="market",
        orders_enabled=False,
        authenticated=True,
        instruments_loaded=True,
        trace_id="t-1",
    )
    status = build_session_status(
        state=BrokerSessionState.HEALTHY,
        connect_status=connect,
        broker_id="paper",
    )
    assert status.state == BrokerSessionState.HEALTHY
    assert status.broker_id == "paper"
    assert status.authenticated is True
    assert status.phase == PHASE_READY_MARKET
    assert status.is_usable is True
    d = status.describe()
    assert d["state"] == "HEALTHY"
    assert d["is_live_ready"] is True
