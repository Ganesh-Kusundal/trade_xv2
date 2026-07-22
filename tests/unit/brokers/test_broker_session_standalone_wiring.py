"""BrokerSession.connect() must self-wire domain ports (ADR-017 root bypass).

Regression guard for a silent failure: connecting via ``BrokerSession.connect()``
directly (not through ``runtime.factory.build()``) left ``domain.ports.async_bridge``
unwired, so Upstox's async websocket/portfolio streams failed with "Async runner
not wired" and only a swallowed ``logger.warning`` — session.status still reported
HEALTHY.
"""

from __future__ import annotations

import pytest

from brokers.session.broker_session import BrokerSession
from domain.ports.async_bridge import run_coro_sync


@pytest.mark.unit
def test_connect_wires_async_runner_standalone():
    session = BrokerSession.connect("paper", load_instruments=False)
    try:
        async def _noop() -> int:
            return 1

        assert run_coro_sync(_noop()) == 1
    finally:
        session.close()
