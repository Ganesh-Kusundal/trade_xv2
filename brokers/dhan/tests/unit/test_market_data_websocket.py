"""Regression tests for ``DhanWebSocketConnectionManager``.

Pre-fix: ``_create_websocket_connection`` silently returned a mock
object that swallowed all data — no warning was emitted. Production
deployments would have believed they were streaming live ticks while
in fact no bytes ever moved.

Post-fix: a WARNING log is emitted every time a stub connection is
created, so operators can detect accidental Phase-0 deployments.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from brokers.dhan.websocket.market_data import DhanWebSocketConnectionManager

pytestmark = pytest.mark.unit


def _build_manager() -> DhanWebSocketConnectionManager:
    return DhanWebSocketConnectionManager(
        url_resolver=MagicMock(),
        token_provider=lambda: "fake-token",
        settings=MagicMock(),
    )


class TestStubWebSocketWarning:
    """``connect()`` must surface that a stub WebSocket is in use."""

    def test_create_websocket_connection_logs_warning(self, caplog) -> None:
        manager = _build_manager()
        with caplog.at_level(logging.WARNING, logger="brokers.dhan.websocket.market_data"):
            manager._create_websocket_connection()

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warning_records, "expected a WARNING-level log from the stub WebSocket"
        joined = " ".join(r.getMessage() for r in warning_records)
        assert "STUB" in joined or "stub" in joined.lower()
