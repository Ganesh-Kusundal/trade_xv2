"""Upstox authenticator implementation.

Wraps the OAuth PKCE-based UpstoxTokenManager for Upstox broker authentication.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from brokers.common.auth.registry import BrokerAuthError, BrokerAuthenticator
from brokers.upstox.auth.config import UpstoxSettingsLoader
from brokers.upstox.auth.token_manager import UpstoxTokenManager

logger = logging.getLogger(__name__)


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
