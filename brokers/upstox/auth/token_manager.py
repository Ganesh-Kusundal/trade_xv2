"""Upstox OAuth 2.0 token lifecycle manager.

Mirrors Trade_J ``UpstoxTokenManager`` — full PKCE flow, refresh-token grant,
proactive refresh using ``refresh_buffer_minutes``, JSON state persistence,
and a webhook upgrade path (Flow 2: Upstox Access Token Request).
"""

from __future__ import annotations

import logging
import threading
import time
from urllib.parse import urlencode

from .exceptions import UpstoxAuthError
from .holders import (
    ThreadSafeTokenHolder,
    TokenSnapshot,
    UpstoxAnalyticsTokenHolder,
    UpstoxExtendedTokenHolder,
    UpstoxStaticTokenHolder,
    UpstoxTokenHolder,
)
from .json_token_state_store import JsonTokenStateStore
from .jwt_expiry import UpstoxJwtExpiry
from .oauth_client import UpstoxOAuthClient
from .pkce import PkcePair, UpstoxPkceUtil
from .token_expiry import UpstoxTokenExpiry

logger = logging.getLogger(__name__)


class UpstoxTokenManager:
    """Upstox token lifecycle: bootstrap, refresh, persist, upgrade-from-webhook.

    Modes (mirrors Trade_J):

    * **STATIC** — fixed access token, no refresh, no 3:30 AM IST fallback.
    * **OAUTH** — bootstrap from configured access+refresh, then refresh proactively.
    * **EXTENDED** — 1-year read-only token, no refresh.
    * **WEBHOOK** — daily token delivered via Upstox notifier URL.
    * **INTERACTIVE** — run PKCE browser flow once at startup.
    """

    def __init__(
        self,
        settings: any,
        oauth_client: UpstoxOAuthClient | None = None,
        state_store: JsonTokenStateStore | None = None,
    ) -> None:
        self._settings = settings
        self._oauth_client = oauth_client or UpstoxOAuthClient(base_url=settings.base_v2)
        self._state_store = state_store or (
            JsonTokenStateStore(settings.token_state_file)
            if getattr(settings, "token_state_file", None)
            else None
        )
        self._lock = threading.RLock()
        self._state: TokenSnapshot | None = None
        self._holder: ThreadSafeTokenHolder = ThreadSafeTokenHolder(self._build_initial_holder())

    def _build_initial_holder(self) -> UpstoxTokenHolder:
        s = self._settings
        if s.analytics_only:
            return UpstoxAnalyticsTokenHolder(s.analytics_token or s.access_token)
        if s.is_extended and s.extended_token:
            return UpstoxExtendedTokenHolder(s.extended_token)
        if s.is_static or (s.access_token and not s.refresh_token):
            return UpstoxStaticTokenHolder(
                s.access_token,
                analytics_only=False,
                label="Upstox access token",
            )
        if s.access_token and s.refresh_token:
            return UpstoxStaticTokenHolder(
                s.access_token,
                analytics_only=False,
                label="Upstox access token (bootstrapped from refresh)",
            )
        return UpstoxStaticTokenHolder("placeholder-no-token")

    @property
    def settings(self) -> any:
        return self._settings

    @property
    def oauth_client(self) -> UpstoxOAuthClient:
        return self._oauth_client

    @property
    def state_store(self) -> JsonTokenStateStore | None:
        return self._state_store

    def get_holder(self) -> UpstoxTokenHolder:
        return self._holder

    def bearer_token(self) -> str:
        self.ensure_valid()
        with self._lock:
            return self._holder.bearer_token()

    def current_token(self) -> str | None:
        with self._lock:
            return self._holder.bearer_token() if self._holder else None

    def current_state(self) -> TokenSnapshot | None:
        with self._lock:
            return self._state

    def ensure_valid(self) -> None:
        with self._lock:
            now_ms = int(time.time() * 1000)
            exp_ms = self._holder.expiry_epoch_ms()
            buffer_ms = getattr(self._settings, "refresh_buffer_minutes", 30) * 60 * 1000
            if exp_ms > 0 and now_ms >= exp_ms - buffer_ms:
                if self._state and self._state.refresh_token:
                    logger.info(
                        "Upstox token at/near expiry; refreshing proactively (now=%d, expiry=%d, buffer=%d)",
                        now_ms,
                        exp_ms,
                        buffer_ms,
                    )
                    self._refresh_now()

    def force_refresh(self) -> TokenSnapshot | None:
        with self._lock:
            if not self._state or not self._state.refresh_token:
                raise UpstoxAuthError("Cannot force_refresh: no refresh token available")
            self._refresh_now()
            return self._state

    def bootstrap(self) -> TokenSnapshot:
        """Acquire the initial state from settings or the persisted JSON file."""
        with self._lock:
            if self._state_store is not None:
                persisted = self._state_store.load()
                if persisted and self._valid_persisted(persisted):
                    self._state = self._from_persisted(persisted)
                    self._holder.replace(
                        UpstoxStaticTokenHolder(
                            self._state.access_token,
                            analytics_only=False,
                            label="Upstox token (persisted)",
                        )
                    )
                    return self._state
            return self._acquire_initial()

    def perform_interactive_oauth(
        self,
        pkce_pair: PkcePair | None = None,
        redirect_uri: str | None = None,
        browser_opener: any | None = None,
    ) -> TokenSnapshot:
        """Build the authorization URL and return the PKCE pair (caller captures the code)."""
        pkce = pkce_pair or UpstoxPkceUtil.generate()
        redirect = redirect_uri or self._settings.redirect_uri
        params = {
            "client_id": self._settings.client_id,
            "redirect_uri": redirect,
            "response_type": "code",
            "code_challenge_method": "S256",
            "code_challenge": pkce.code_challenge,
        }
        auth_url = (
            f"{self._oauth_client._base_url}/v2/login/authorization/dialog?{urlencode(params)}"
        )
        if browser_opener is not None:
            try:
                browser_opener(auth_url)
            except Exception:
                logger.info("Could not open browser automatically; copy URL manually")
        return pkce

    def complete_interactive_oauth(
        self, code: str, pkce_pair: PkcePair, redirect_uri: str | None = None
    ) -> TokenSnapshot:
        """Exchange the captured auth code for an access+refresh token pair."""
        resp = self._oauth_client.exchange_code(
            code=code,
            client_id=self._settings.client_id,
            client_secret=self._settings.client_secret,
            redirect_uri=redirect_uri or self._settings.redirect_uri,
            code_verifier=pkce_pair.code_verifier,
        )
        new_state = TokenSnapshot(
            access_token=resp.access_token,
            refresh_token=resp.refresh_token,
            expires_at_ms=int(time.time() * 1000) + resp.expires_in_seconds * 1000,
            issued_at_ms=resp.issued_at_ms,
            source="OAUTH",
        )
        with self._lock:
            self._state = new_state
            self._holder.replace(
                UpstoxStaticTokenHolder(
                    new_state.access_token,
                    analytics_only=False,
                    label="Upstox token (interactive)",
                )
            )
            self._persist(new_state)
        return new_state

    def upgrade_from_webhook(self, access_token: str, expires_at_ms: int) -> bool:
        """Replace the current state with a webhook-delivered token.

        Mirrors Trade_J ``UpstoxTokenManager.upgradeFromWebhook`` semantics:
        only replaces if current is None, expired, or the new one expires later.
        """
        if not access_token or not access_token.strip():
            raise ValueError("accessToken must not be blank")
        if expires_at_ms <= 0:
            raise ValueError("expiresAtMs must be positive")
        with self._lock:
            current = self._state
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
            self._state = new_state
            self._holder.replace(
                UpstoxStaticTokenHolder(
                    access_token,
                    analytics_only=False,
                    label="Upstox token (webhook)",
                )
            )
            self._persist(new_state)
            logger.info("Upstox token upgraded via webhook; expiresAt=%d", expires_at_ms)
            return True

    def invalidate(self, access_token: str | None = None) -> bool:
        """Reject ad-hoc invalidation if a fresher token already exists.

        Mirrors Trade_J ``TokenLifecycleService.invalidate`` policy.
        """
        with self._lock:
            current = self._state
            if current is None:
                return True
            if access_token and access_token != current.access_token:
                logger.debug(
                    "invalidate ignored — current token does not match supplied access_token"
                )
                return False
            now_ms = int(time.time() * 1000)
            return not (current.expires_at_ms and current.expires_at_ms > now_ms)

    @classmethod
    def create_extended(cls, extended_token: str) -> UpstoxExtendedTokenHolder:
        return UpstoxExtendedTokenHolder(extended_token)

    @classmethod
    def create_analytics(cls, analytics_token: str) -> UpstoxAnalyticsTokenHolder:
        return UpstoxAnalyticsTokenHolder(analytics_token)

    @classmethod
    def create_static(cls, access_token: str) -> UpstoxStaticTokenHolder:
        return UpstoxStaticTokenHolder(access_token)

    def _acquire_initial(self) -> TokenSnapshot:
        s = self._settings
        if s.access_token:
            if s.refresh_token:
                exp = self._oauth_client.fetch_profile(s.access_token)
                if exp <= 0:
                    exp = UpstoxJwtExpiry.parse_expiry_epoch_ms(s.access_token)
                if exp <= 0:
                    exp = UpstoxTokenExpiry.next_expiry_epoch_ms()
                state = TokenSnapshot(
                    access_token=s.access_token,
                    refresh_token=s.refresh_token,
                    expires_at_ms=exp,
                    issued_at_ms=int(time.time() * 1000),
                    source="OAUTH",
                )
                self._state = state
                self._holder.replace(
                    UpstoxStaticTokenHolder(
                        s.access_token, analytics_only=False, label="Upstox token (bootstrap)"
                    )
                )
                self._persist(state)
                return state
            jwt_exp = UpstoxJwtExpiry.parse_expiry_epoch_ms(s.access_token)
            exp = jwt_exp if jwt_exp > 0 else UpstoxTokenExpiry.next_expiry_epoch_ms()
            state = TokenSnapshot(
                access_token=s.access_token,
                refresh_token=None,
                expires_at_ms=exp,
                issued_at_ms=int(time.time() * 1000),
                source="STATIC",
            )
            self._state = state
            self._holder.replace(
                UpstoxStaticTokenHolder(s.access_token, analytics_only=False, label="Upstox token")
            )
            self._persist(state)
            return state
        raise UpstoxAuthError(
            "No Upstox access token available. Paste UPSTOX_ACCESS_TOKEN in env or run "
            "performInteractiveOAuth()."
        )

    def _refresh_now(self) -> None:
        state = self._state
        if state is None or not state.refresh_token:
            raise UpstoxAuthError("Cannot refresh token: no refresh token available")
        resp = self._oauth_client.refresh_token(
            refresh_token=state.refresh_token,
            client_id=self._settings.client_id,
            client_secret=self._settings.client_secret,
        )
        new_state = TokenSnapshot(
            access_token=resp.access_token,
            refresh_token=resp.refresh_token,
            expires_at_ms=int(time.time() * 1000) + resp.expires_in_seconds * 1000,
            issued_at_ms=resp.issued_at_ms,
            source="OAUTH",
        )
        self._state = new_state
        self._holder.replace(
            UpstoxStaticTokenHolder(
                new_state.access_token, analytics_only=False, label="Upstox token (refreshed)"
            )
        )
        self._persist(new_state)

    def _persist(self, state: TokenSnapshot) -> None:
        if self._state_store is None:
            return
        try:
            self._state_store.save(
                {
                    "access_token": state.access_token,
                    "refresh_token": state.refresh_token,
                    "expires_at_ms": state.expires_at_ms,
                    "issued_at_ms": state.issued_at_ms,
                    "source": state.source,
                }
            )
        except OSError as exc:
            logger.warning("Failed to persist Upstox token state: %s", exc)

    def _valid_persisted(self, persisted: dict) -> bool:
        if not isinstance(persisted, dict):
            return False
        token = persisted.get("access_token")
        if not token or not isinstance(token, str):
            return False
        exp = int(persisted.get("expires_at_ms", 0) or 0)
        return exp > int(time.time() * 1000)

    def _from_persisted(self, persisted: dict) -> TokenSnapshot:
        return TokenSnapshot(
            access_token=persisted["access_token"],
            refresh_token=persisted.get("refresh_token"),
            expires_at_ms=int(persisted.get("expires_at_ms", 0)),
            issued_at_ms=int(persisted.get("issued_at_ms", 0)),
            source=str(persisted.get("source", "OAUTH")),
        )
