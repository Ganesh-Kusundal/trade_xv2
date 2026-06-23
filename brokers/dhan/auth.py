"""Dhan authenticator implementation.

Wraps the TOTP-based AuthManager for Dhan broker authentication.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from brokers.common.auth.registry import BrokerAuthError, BrokerAuthenticator
from brokers.common.auth import AuthManager, JsonTokenStateStore, TokenSource

logger = logging.getLogger(__name__)


class DhanAuthenticator:
    """Adapter around :class:`AuthManager` for Dhan (TOTP-based)."""

    def __init__(
        self,
        env_path: Path | None = None,
        on_token_refresh: Callable[[str], None] | None = None,
    ) -> None:
        from brokers.dhan.settings import DhanSettingsLoader

        self._env_path = env_path
        self._store_path = Path("runtime/dhan-token.json")
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        self._refresh_callbacks: list[Callable[[str], None]] = []
        if on_token_refresh is not None:
            self._refresh_callbacks.append(on_token_refresh)

        # Load settings for TOTP generation
        self._settings = DhanSettingsLoader.from_env(env_path=env_path)

        # Build the underlying AuthManager
        self._auth = AuthManager(
            client_id=self._settings.client_id,
            token_store=JsonTokenStateStore(self._store_path),
            token_source=TokenSource.TOTP,
            on_acquire=lambda: self._fetch_via_totp(),
            on_refresh=lambda: self._fetch_via_totp(),
            token_lifetime_seconds=self._settings.token_lifetime_seconds,
        )
        self._auth.on_refresh(
            lambda: self._fire_refresh(self._auth.state.access_token if self._auth.state else "")
        )

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

    def _fetch_via_totp(self) -> str | None:
        """Generate a Dhan access token via TOTP using settings."""
        from brokers.dhan.token_manager import generate_totp_token

        token = generate_totp_token(self._settings)
        if token is None:
            raise BrokerAuthError("Failed to generate TOTP token")
        return token
