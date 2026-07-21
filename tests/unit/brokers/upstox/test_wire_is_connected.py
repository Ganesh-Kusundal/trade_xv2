"""Tests for UpstoxWireAdapter ``is_connected`` — unified liveness contract.

Uses a minimal fake broker (no full ``UpstoxBroker`` construction needed) to
verify that ``is_connected`` now requires BOTH a CONNECTED status AND a usable
(current) token, instead of trusting the status flag alone.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from brokers.providers.upstox.wire import UpstoxWireAdapter
from domain import ConnectionStatus


class _FakeBroker:
    """Minimal stand-in for UpstoxBroker for the ``is_connected`` contract."""

    def __init__(self, status: ConnectionStatus, token: str | None) -> None:
        self.status = status
        self._token = token
        self.token_manager = MagicMock()
        self.token_manager.current_token.return_value = token


def _gateway(status: ConnectionStatus, token: str | None) -> UpstoxWireAdapter:
    # ``UpstoxWireAdapter.__init__`` builds many adapters from the broker; we
    # only exercise ``is_connected``, so bypass init via object construction.
    gw = UpstoxWireAdapter.__new__(UpstoxWireAdapter)
    gw._broker = _FakeBroker(status, token)
    return gw


def test_is_connected_true_when_connected_and_token_present() -> None:
    gw = _gateway(ConnectionStatus.CONNECTED, "valid-token")
    assert gw.is_connected is True


def test_is_connected_false_when_not_connected() -> None:
    gw = _gateway(ConnectionStatus.DISCONNECTED, "valid-token")
    assert gw.is_connected is False


def test_is_connected_false_when_token_missing() -> None:
    """Regression: status CONNECTED but expired/empty token must read False."""
    gw = _gateway(ConnectionStatus.CONNECTED, "")
    assert gw.is_connected is False


def test_is_connected_false_when_token_none() -> None:
    gw = _gateway(ConnectionStatus.CONNECTED, None)
    assert gw.is_connected is False
