"""Interactive OAuth (PKCE) and webhook-upgrade flows for ``UpstoxTokenManager``.

Extracted from ``UpstoxTokenManager`` so the interactive/upgrade paths are
isolated from refresh and persistence logic.
"""

from __future__ import annotations

import logging
import time
from urllib.parse import urlencode

from .holders import TokenSnapshot, UpstoxStaticTokenHolder
from .pkce import PkcePair, UpstoxPkceUtil

logger = logging.getLogger(__name__)


class OAuthFlow:
    """Interactive PKCE OAuth and webhook token upgrade."""

    def __init__(self, manager: any) -> None:
        self._m = manager

    def perform_interactive(
        self,
        pkce_pair: PkcePair | None = None,
        redirect_uri: str | None = None,
        browser_opener: any | None = None,
    ) -> PkcePair:
        """Build the authorization URL and return the PKCE pair (caller captures the code)."""
        m = self._m
        pkce = pkce_pair or UpstoxPkceUtil.generate()
        redirect = redirect_uri or m._settings.redirect_uri
        params = {
            "client_id": m._settings.client_id,
            "redirect_uri": redirect,
            "response_type": "code",
            "code_challenge_method": "S256",
            "code_challenge": pkce.code_challenge,
        }
        auth_url = f"{m._oauth_client._base_url}/v2/login/authorization/dialog?{urlencode(params)}"
        if browser_opener is not None:
            try:
                browser_opener(auth_url)
            except Exception:
                logger.info("Could not open browser automatically; copy URL manually")
        return pkce

    def complete_interactive(
        self, code: str, pkce_pair: PkcePair, redirect_uri: str | None = None
    ) -> TokenSnapshot:
        """Exchange the captured auth code for an access+refresh token pair."""
        m = self._m
        resp = m._oauth_client.exchange_code(
            code=code,
            client_id=m._settings.client_id,
            client_secret=m._settings.client_secret,
            redirect_uri=redirect_uri or m._settings.redirect_uri,
            code_verifier=pkce_pair.code_verifier,
        )
        new_state = TokenSnapshot(
            access_token=resp.access_token,
            refresh_token=resp.refresh_token,
            expires_at_ms=int(time.time() * 1000) + resp.expires_in_seconds * 1000,
            issued_at_ms=resp.issued_at_ms,
            source="OAUTH",
        )
        with m._lock:
            m._state = new_state
            m._holder.replace(
                UpstoxStaticTokenHolder(
                    new_state.access_token,
                    analytics_only=False,
                    label="Upstox token (interactive)",
                )
            )
            self._m._persist(new_state)
        return new_state

    def upgrade_from_webhook(self, access_token: str, expires_at_ms: int) -> bool:
        """Replace the current state with a webhook-delivered token.

        Mirrors Trade_J ``UpstoxTokenManager.upgradeFromWebhook`` semantics:
        only replaces if current is None, expired, or the new one expires later.
        """
        m = self._m
        if not access_token or not access_token.strip():
            raise ValueError("accessToken must not be blank")
        if expires_at_ms <= 0:
            raise ValueError("expiresAtMs must be positive")
        with m._lock:
            current = m._state
            now_ms = int(time.time() * 1000)
            should_replace = (
                current is None
                or current.expires_at_ms <= now_ms
                or expires_at_ms > current.expires_at_ms
            )
            if not should_replace:
                logger.debug(
                    "upgradeFromWebhook skipped — incoming expiry %d <= current %d",
                    expires_at_ms,
                    current.expires_at_ms if current else 0,
                )
                return False
            preserved_refresh = current.refresh_token if current else None
            new_state = TokenSnapshot(
                access_token=access_token,
                refresh_token=preserved_refresh,
                expires_at_ms=expires_at_ms,
                issued_at_ms=now_ms,
                source="WEBHOOK",
            )
            m._state = new_state
            m._holder.replace(
                UpstoxStaticTokenHolder(
                    access_token,
                    analytics_only=False,
                    label="Upstox token (webhook)",
                )
            )
            self._m._persist(new_state)
            logger.info("Upstox token upgraded via webhook; expiresAt=%d", expires_at_ms)
            return True
