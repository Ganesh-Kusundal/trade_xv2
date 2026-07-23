"""Shared connection-liveness contract — additive mixin, not an ABC.

Dhan and Upstox connections each track ``_connected``/``_authenticated``
independently; nothing stops one from silently redefining what ``is_connected``
means (e.g. WS-liveness-only vs a post-bootstrap flag that stays True after the
token expires — this exact drift happened once in the legacy broker layer).
This mixin pins ONE meaning: authenticated + primary transport alive.

Subclasses keep setting ``_connected``/``_authenticated`` exactly as before;
only override ``_transport_connected()`` if liveness needs to mean more than
that (e.g. re-checking token expiry or streaming health).
"""

from __future__ import annotations


class ConnectionLiveness:
    _connected: bool = False
    _authenticated: bool = False

    def _transport_connected(self) -> bool:
        """Subclass hook — default: connected flag set and authentication succeeded."""
        return self._connected and self._authenticated

    @property
    def is_connected(self) -> bool:
        return bool(self._transport_connected())
