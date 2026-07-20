"""Shared live certification probe tests for all brokers."""

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
@pytest.mark.parametrize("broker", ["dhan", "upstox"])
def test_live_token_probes(broker: str) -> None:
    session = _open_or_skip(broker)
    try:
        probe_token_refresh(session)
        probe_token_expiry(session)
    finally:
        session.close()


@pytest.mark.integration
@pytest.mark.live_readonly
@pytest.mark.parametrize("broker", ["dhan", "upstox"])
def test_live_reconnect_probes(broker: str) -> None:
    session = _open_or_skip(broker)
    try:
        probe_reconnect(session)
        probe_session_recovery(session)
    finally:
        session.close()
