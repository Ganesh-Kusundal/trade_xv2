"""Unit tests for live certification probes (offline / paper)."""

from __future__ import annotations

import pytest

from brokers.certification.live_probes import (
    probe_reconnect,
    probe_session_recovery,
    probe_token_expiry,
    probe_token_refresh,
)
from brokers.session import BrokerSession
from domain.ports.broker_session_state import BrokerSessionState


@pytest.mark.unit
@pytest.mark.certification
def test_live_probes_na_on_paper_via_suite_helpers() -> None:
    from brokers.certification.suite import (
        _disconnect,
        _reconnect,
        _session_recovery,
        _token_expiry,
        _token_refresh,
    )

    session = BrokerSession("paper")
    try:
        assert "N/A" in _token_refresh(session)
        assert "N/A" in _token_expiry(session)
        assert "N/A" in _reconnect(session)
        assert "N/A" in _disconnect(session)
        assert "N/A" in _session_recovery(session)
    finally:
        session.close()


@pytest.mark.unit
@pytest.mark.certification
def test_paper_reconnect_probe_restores_healthy() -> None:
    session = BrokerSession("paper")
    try:
        assert session.session_state == BrokerSessionState.HEALTHY
        detail = probe_reconnect(session)
        assert session.session_state == BrokerSessionState.HEALTHY
        assert "reconnected" in detail
    finally:
        session.close()


@pytest.mark.unit
@pytest.mark.certification
def test_paper_token_probes_authenticated() -> None:
    session = BrokerSession("paper")
    try:
        assert "authenticated" in probe_token_refresh(session).lower() or "refresh" in probe_token_refresh(session).lower()
        assert probe_token_expiry(session)
    finally:
        session.close()


@pytest.mark.unit
@pytest.mark.certification
def test_paper_session_recovery_cycle() -> None:
    session = BrokerSession("paper")
    try:
        detail = probe_session_recovery(session)
        assert "recovery ok" in detail
        assert session.session_state == BrokerSessionState.HEALTHY
    finally:
        session.close()
