"""Live certification probe integration tests for Upstox (marker-gated)."""

from __future__ import annotations

import pytest

from brokers.certification.live_probes import (
    probe_reconnect,
    probe_session_recovery,
    probe_token_expiry,
    probe_token_refresh,
)
from brokers.session import BrokerSession


def _open_or_skip(broker: str) -> BrokerSession:
    try:
        return BrokerSession(broker, mode="market")
    except Exception as exc:
        pytest.skip(f"{broker} live session unavailable: {exc}")


@pytest.mark.integration
@pytest.mark.live_readonly
@pytest.mark.upstox
def test_upstox_live_token_probes() -> None:
    session = _open_or_skip("upstox")
    try:
        probe_token_refresh(session)
        probe_token_expiry(session)
    finally:
        session.close()


@pytest.mark.integration
@pytest.mark.live_readonly
@pytest.mark.upstox
def test_upstox_live_reconnect_probes() -> None:
    session = _open_or_skip("upstox")
    try:
        probe_reconnect(session)
        probe_session_recovery(session)
    finally:
        session.close()
