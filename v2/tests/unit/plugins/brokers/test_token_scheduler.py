"""Regression tests: TokenRefreshScheduler lifecycle wired into connections.

connect() must start the background refresh scheduler; disconnect() must stop it.
No network is touched — start() spawns a daemon thread whose only work happens
after ``interval_seconds``, so construction + connect/disconnect stay offline.
"""

from __future__ import annotations

from plugins.brokers.common.token_lifecycle import TokenRefreshScheduler
from plugins.brokers.dhan.config import DhanConfig
from plugins.brokers.dhan.connection import DhanConnection
from plugins.brokers.upstox.config import UpstoxConfig
from plugins.brokers.upstox.connection import UpstoxConnection


def test_dhan_connection_starts_and_stops_scheduler() -> None:
    conn = DhanConnection(DhanConfig())
    assert isinstance(conn._scheduler, TokenRefreshScheduler)
    assert conn._scheduler.broker_id == "dhan"
    assert conn._scheduler.is_running is False

    conn.connect()
    try:
        assert conn._scheduler.is_running is True
    finally:
        conn.disconnect()
    assert conn._scheduler.is_running is False


def test_upstox_connection_starts_and_stops_scheduler() -> None:
    conn = UpstoxConnection(UpstoxConfig())
    assert isinstance(conn._scheduler, TokenRefreshScheduler)
    assert conn._scheduler.broker_id == "upstox"
    assert conn._scheduler.is_running is False

    conn.connect()
    try:
        assert conn._scheduler.is_running is True
    finally:
        conn.disconnect()
    assert conn._scheduler.is_running is False
