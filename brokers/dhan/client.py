"""Dhan Client Holder — token rotation callback hub.

Holds the ``DhanTokenManager`` and dispatches
:class:`TokenRotationListener` callbacks whenever a new access token is
acquired, so all adapters can refresh their view of the token synchronously.

Design reference: Trade_J ``DhanClientHolder`` (token rotation observable).
"""

from __future__ import annotations

import time

from brokers.dhan.auth.auth import DhanTokenManager, DhanTokenProvider


class TokenRotationListener:
    """Callback interface invoked on every token rotation event.

    Register implementations via :meth:`DhanClientHolder.add_listener`.
    """

    def on_token_acquired(self, access_token: str, issued_at_ms: int) -> None:
        """Called when a fresh access token has been acquired.

        :param access_token: The new access token.
        :param issued_at_ms: Unix-epoch milliseconds when the token was issued.
        """
        ...

    def on_token_expired(self, access_token: str) -> None:
        """Called when the current token has been confirmed expired or rejected."""
        ...

    def on_token_error(self, error: Exception) -> None:
        """Called when token acquisition fails after all retries."""
        ...


class DhanClientHolder(DhanTokenProvider):
    """Wraps ``DhanTokenManager`` and broadcasts token changes to listeners.

    The holder owns the single source-of-truth token provider callable.
    Adapters (HTTP client, SDK context) receive this callable at construction
    so they always pick up the latest token without needing polling or
    periodic resync.
    """

    def __init__(
        self,
        token_manager: DhanTokenManager,
        *,
        clock_skew_tolerance_ms: int = 30_000,
    ) -> None:
        self._token_manager = token_manager
        self._clock_skew_tolerance_ms = clock_skew_tolerance_ms
        self._listeners: list[TokenRotationListener] = []
        self._last_token: str | None = None
        self._last_issued_at_ms: int = 0
        self._last_refresh_ms: int = 0

    # ── Token access ─────────────────────────────────────────────────

    def ensure_valid_and_get(self) -> str:
        """Atomically ensure validity and return the current access token."""
        token = self._token_manager.ensure_valid_and_get()
        if token != self._last_token:
            self._last_token = token
            issued_at_ms = int(time.time() * 1000)
            self._last_issued_at_ms = issued_at_ms
            self._last_refresh_ms = issued_at_ms
            self._notify_acquired(token, issued_at_ms)
        return token

    def get_access_token(self) -> str:
        """Return the current valid access token, refreshing if needed."""
        return self.ensure_valid_and_get()

    def ensure_valid(self) -> None:
        """Force a validity check; raises ``ValueError`` if no token is available."""
        self._token_manager.ensure_valid()

    def token_generation_id(self) -> int:
        return self._token_manager.token_generation_id()

    def invalidate_generation(self, failed_generation_id: int) -> bool:
        prev, self._last_token = self._last_token, None
        invalidated = self._token_manager.invalidate_generation(failed_generation_id)
        if invalidated and prev:
            self._notify_expired(prev)
        return invalidated

    def invalidate(self) -> None:
        """Invalidate the current token and notify listeners."""
        prev, self._last_token = self._last_token, None
        self._token_manager.invalidate()
        if prev:
            self._notify_expired(prev)

    # ── Listener management ──────────────────────────────────────────

    def add_listener(self, listener: TokenRotationListener) -> None:
        """Register a listener for token life-cycle events."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: TokenRotationListener) -> None:
        """Unregister a previously registered listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    # ── State inspection ─────────────────────────────────────────────

    @property
    def current_token(self) -> str | None:
        """The last-seen access token (may be ``None`` before first call to :meth:`get_access_token`)."""
        return self._last_token

    @property
    def last_issued_at_ms(self) -> int:
        """Unix-epoch ms of the last token acquisition event."""
        return self._last_issued_at_ms

    @property
    def time_since_refresh_ms(self) -> int:
        """Milliseconds since the last token refresh call."""
        return max(0, int(time.time() * 1000) - self._last_refresh_ms)

    # ── Private ──────────────────────────────────────────────────────

    def _notify_acquired(self, token: str, issued_at_ms: int) -> None:
        for listener in list(self._listeners):
            try:
                listener.on_token_acquired(token, issued_at_ms)
            except Exception:
                continue  # listener failure must not break token flow

    def _notify_expired(self, token: str) -> None:
        for listener in list(self._listeners):
            try:
                listener.on_token_expired(token)
            except Exception:
                continue
