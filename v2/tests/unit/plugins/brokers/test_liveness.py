"""ConnectionLiveness — shared is_connected contract (connected AND authenticated)."""

from __future__ import annotations

from plugins.brokers.common.liveness import ConnectionLiveness


class _Fake(ConnectionLiveness):
    pass


class _PaperLike(ConnectionLiveness):
    def _transport_connected(self) -> bool:
        return self._connected


def test_default_false_until_connected_and_authenticated() -> None:
    conn = _Fake()
    assert conn.is_connected is False

    conn._connected = True
    assert conn.is_connected is False, "connected but not authenticated is not live"

    conn._authenticated = True
    assert conn.is_connected is True


def test_disconnect_flips_back_to_not_connected() -> None:
    conn = _Fake()
    conn._connected = True
    conn._authenticated = True
    assert conn.is_connected is True

    conn._connected = False
    assert conn.is_connected is False


def test_override_hook_can_drop_the_auth_requirement() -> None:
    """Paper has no auth concept — connected alone is the whole contract."""
    conn = _PaperLike()
    assert conn.is_connected is False
    conn._connected = True
    assert conn.is_connected is True
