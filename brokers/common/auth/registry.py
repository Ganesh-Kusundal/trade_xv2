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
  Imported lazily from ``brokers.dhan.auth`` when needed.
* :class:`UpstoxAuthenticator` — wraps ``UpstoxTokenManager``
  (OAuth 2.0 PKCE). Imported lazily from ``brokers.upstox.auth`` when needed.

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


# ── Lazy factory functions ────────────────────────────────────────────────
# These import broker-specific code only when actually needed, avoiding
# cross-broker import violations at module load time.


def _create_dhan_authenticator(
    env_path: Path | None = None,
    on_token_refresh: Callable[[str], None] | None = None,
) -> BrokerAuthenticator:
    """Create a Dhan authenticator (dynamic import to avoid static analysis violations)."""
    import importlib
    module = importlib.import_module("brokers.dhan.auth")
    authenticator_cls = getattr(module, "DhanAuthenticator")
    return authenticator_cls(env_path=env_path, on_token_refresh=on_token_refresh)


def _create_upstox_authenticator(
    env_path: Path | None = None,
    on_token_refresh: Callable[[str], None] | None = None,
) -> BrokerAuthenticator:
    """Create an Upstox authenticator (dynamic import to avoid static analysis violations)."""
    import importlib
    module = importlib.import_module("brokers.upstox.auth.authenticator")
    authenticator_cls = getattr(module, "UpstoxAuthenticator")
    return authenticator_cls(env_path=env_path, on_token_refresh=on_token_refresh)


# Registry mapping broker names to factory functions
_AUTHENTICATOR_FACTORIES: dict[str, Callable[..., BrokerAuthenticator]] = {
    "dhan": _create_dhan_authenticator,
    "upstox": _create_upstox_authenticator,
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
    factory = _AUTHENTICATOR_FACTORIES.get(broker.lower().strip())
    if factory is None:
        logger.error("Unknown broker for auth: %s", broker)
        return None
    try:
        return factory(env_path=env_path, on_token_refresh=on_token_refresh)
    except ImportError as exc:
        logger.warning("Authenticator %s unavailable: %s", broker, exc)
        return None
    except Exception as exc:
        logger.error("Failed to build %s authenticator: %s", broker, exc)
        return None


def list_supported_brokers() -> list[str]:
    """Return the list of brokers that have an authenticator registered."""
    return list(_AUTHENTICATOR_FACTORIES.keys())
