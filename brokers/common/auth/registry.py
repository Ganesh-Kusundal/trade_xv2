"""BrokerAuthenticator — common auth interface for every broker.

Phase 7: replaces the implicit dual implementation where Dhan uses
:class:`brokers.common.core.auth.AuthManager` and Upstox uses
:class:`brokers.upstox.auth.token_manager.UpstoxTokenManager`. The
two implementations serve the same purpose (acquire, persist, refresh
tokens) but had no shared protocol. This module defines a thin
:class:`BrokerAuthenticator` protocol that both implementations
satisfy so callers (CLI ``doctor``, lifecycle, brokers registry) can
treat them uniformly.

Concrete implementations
------------------------

* :class:`DhanAuthenticator` — wraps ``AuthManager`` (TOTP-based).
* :class:`UpstoxAuthenticator` — wraps ``UpstoxTokenManager``
  (OAuth 2.0 PKCE).

Both implementations expose the same surface so callers do not need
to know which broker they are dealing with.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class BrokerAuthenticator(Protocol):
    """The common broker auth interface.

    A :class:`BrokerAuthenticator` is responsible for:

    * Acquiring an access token for the broker (TOTP, OAuth, etc.)
    * Persisting the token so restarts do not require re-auth
    * Refreshing the token before it expires
    * Notifying subscribers on token refresh (so WebSocket
      services can push the fresh token through ``update_token``)

    This protocol is intentionally minimal: anything more specific
    (PKCE pair generation, TOTP secret validation) lives in the
    concrete implementation.
    """

    @property
    def broker_name(self) -> str:
        """The broker identifier (``"dhan"``, ``"upstox"``)."""
        ...

    def acquire(self) -> str:
        """Acquire (or refresh) an access token. Returns the token string.

        Raises
        ------
        BrokerAuthError
            When credentials are missing, the broker rejected the
            request, or the persisted state is unrecoverable.
        """
        ...

    def is_authenticated(self) -> bool:
        """``True`` when a fresh token is currently available."""
        ...

    def ensure_valid(self) -> bool:
        """Refresh if expired. Returns ``True`` if the token is fresh."""
        ...

    def on_refresh(self, callback: Callable[[str], None]) -> None:
        """Register a callback invoked with the new token after a refresh.

        Used by ``BrokerConnection`` / WebSocket services to push
        the fresh token through ``update_token``.
        """
        ...


class BrokerAuthError(RuntimeError):
    """Raised by :class:`BrokerAuthenticator.acquire` on unrecoverable failure."""


# ── Dhan implementation ────────────────────────────────────────────────────


class DhanAuthenticator:
    """Adapter around :class:`AuthManager` for Dhan (TOTP-based)."""

    def __init__(
        self,
        env_path: Path | None = None,
        on_token_refresh: Callable[[str], None] | None = None,
    ) -> None:
        from brokers.common.core.auth import (
            AuthManager,
            JsonTokenStateStore,
            TokenSource,
        )

        self._env_path = env_path
        self._store_path = Path("runtime/dhan-token.json")
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        self._refresh_callbacks: list[Callable[[str], None]] = []
        if on_token_refresh is not None:
            self._refresh_callbacks.append(on_token_refresh)

        # Build the underlying AuthManager. The actual
        # ``on_acquire`` lambda is wired in ``acquire`` because it
        # needs access to the env file path.
        self._auth = AuthManager(
            client_id="dhan",  # placeholder; ``acquire`` reads .env.local
            token_store=JsonTokenStateStore(self._store_path),
            token_source=TokenSource.STATIC,
            on_acquire=lambda: self._fetch_via_totp(),
            on_refresh=lambda: self._fetch_via_totp(),
        )
        # Bridge: wire AuthManager's internal callbacks to ours so
        # ``on_refresh`` registrations see fresh tokens.
        # AuthManager.on_refresh takes a no-arg callable; we look
        # up the current token from state when invoked.
        self._auth.on_refresh(lambda: self._fire_refresh(self._auth.state.access_token if self._auth.state else ""))

    @property
    def broker_name(self) -> str:
        return "dhan"

    def acquire(self) -> str:
        try:
            return self._auth.acquire()
        except Exception as exc:
            raise BrokerAuthError(f"Dhan auth failed: {exc}") from exc

    def is_authenticated(self) -> bool:
        return bool(self._auth.is_authenticated)

    def ensure_valid(self) -> bool:
        return self._auth.ensure_valid()

    def on_refresh(self, callback: Callable[[str], None]) -> None:
        self._refresh_callbacks.append(callback)

    def _fire_refresh(self, token: str) -> None:
        for cb in list(self._refresh_callbacks):
            try:
                cb(token)
            except Exception as exc:
                logger.debug("dhan_on_refresh_callback_failed: %s", exc)

    def _fetch_via_totp(self) -> str:
        """Generate a Dhan access token via TOTP using env credentials."""
        from brokers.dhan.factory import _generate_totp_token

        return _generate_totp_token(self._env_path)


# ── Upstox implementation ─────────────────────────────────────────────────


class UpstoxAuthenticator:
    """Adapter around :class:`UpstoxTokenManager` for Upstox (OAuth PKCE)."""

    def __init__(
        self,
        env_path: Path | None = None,
        on_token_refresh: Callable[[str], None] | None = None,
    ) -> None:
        self._env_path = env_path
        self._refresh_callbacks: list[Callable[[str], None]] = []
        if on_token_refresh is not None:
            self._refresh_callbacks.append(on_token_refresh)

        from brokers.upstox.auth.config import UpstoxSettingsLoader
        from brokers.upstox.auth.token_manager import UpstoxTokenManager

        self._settings = UpstoxSettingsLoader.from_env(
            env_path=str(env_path) if env_path else None,
        )
        self._mgr = UpstoxTokenManager(self._settings)

    @property
    def broker_name(self) -> str:
        return "upstox"

    def acquire(self) -> str:
        try:
            token = self._mgr.bootstrap()
        except Exception as exc:
            raise BrokerAuthError(f"Upstox auth failed: {exc}") from exc
        # Notify subscribers so WebSocket services can update.
        self._fire_refresh(token)
        return token

    def is_authenticated(self) -> bool:
        try:
            return bool(self._mgr.access_token())
        except Exception:
            return False

    def ensure_valid(self) -> bool:
        try:
            return self._mgr.ensure_valid_token()
        except Exception:
            return False

    def on_refresh(self, callback: Callable[[str], None]) -> None:
        self._refresh_callbacks.append(callback)

    def _fire_refresh(self, token: str) -> None:
        for cb in list(self._refresh_callbacks):
            try:
                cb(token)
            except Exception as exc:
                logger.debug("upstox_on_refresh_callback_failed: %s", exc)


# ── Registry ───────────────────────────────────────────────────────────────


_AUTHENTICATORS: dict[str, type[BrokerAuthenticator]] = {
    "dhan": DhanAuthenticator,
    "upstox": UpstoxAuthenticator,
}


def create_authenticator(
    broker: str,
    *,
    env_path: Path | None = None,
    on_token_refresh: Callable[[str], None] | None = None,
) -> BrokerAuthenticator | None:
    """Create an authenticator for *broker*.

    Returns ``None`` when the broker is not registered or its
    dependencies are missing.
    """
    cls = _AUTHENTICATORS.get(broker.lower().strip())
    if cls is None:
        logger.error("Unknown broker for auth: %s", broker)
        return None
    try:
        return cls(env_path=env_path, on_token_refresh=on_token_refresh)
    except ImportError as exc:
        logger.warning("Authenticator %s unavailable: %s", broker, exc)
        return None
    except Exception as exc:
        logger.error("Failed to build %s authenticator: %s", broker, exc)
        return None


def list_supported_brokers() -> list[str]:
    """Return the list of brokers that have an authenticator registered."""
    return list(_AUTHENTICATORS.keys())