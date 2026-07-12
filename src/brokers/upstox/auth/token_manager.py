"""Upstox OAuth 2.0 token lifecycle manager.

Mirrors Trade_J ``UpstoxTokenManager`` — full PKCE flow, refresh-token grant,
proactive refresh using ``refresh_buffer_minutes``, JSON state persistence,
and a webhook upgrade path (Flow 2: Upstox Access Token Request).

This module is a thin facade: holder construction, refresh orchestration,
interactive OAuth, and persistence live in focused submodules
(``holder_factory``, ``token_refresher``, ``oauth_flow``, ``token_persistence``).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from infrastructure.auth.jwt_expiry import JwtExpiry

from .exceptions import UpstoxAuthError
from .holder_factory import TokenHolderFactory
from .holders import (
    ThreadSafeTokenHolder,
    TokenSnapshot,
    UpstoxAnalyticsTokenHolder,
    UpstoxExtendedTokenHolder,
    UpstoxStaticTokenHolder,
    UpstoxTokenHolder,
)
from .json_token_state_store import JsonTokenStateStore
from .oauth_client import UpstoxOAuthClient
from .oauth_flow import OAuthFlow
from .pkce import PkcePair
from .token_persistence import TokenPersistence
from .token_refresher import TokenRefresher

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
        refresh_lock: threading.Lock | None = None,
    ) -> None:
        self._settings = settings
        self._oauth_client = oauth_client or UpstoxOAuthClient(base_url=settings.base_v2)
        self._state_store = state_store or (
            JsonTokenStateStore(settings.token_state_file)
            if getattr(settings, "token_state_file", None)
            else None
        )
        self._lock = threading.RLock()
        self._refresh_lock = refresh_lock or threading.Lock()
        self._refresh_done = threading.Event()
        self._refresh_done.set()
        self._state: TokenSnapshot | None = None
        self._holder: ThreadSafeTokenHolder = ThreadSafeTokenHolder(
            TokenHolderFactory().build_initial(settings)
        )
        # Tracks last access_token that already saw a 401 (soft-retry once, then mint).
        self._last_401_token: str | None = None

        # Delegated responsibility groups.
        self._factory = TokenHolderFactory()
        self._refresher = TokenRefresher(self)
        self._oauth = OAuthFlow(self)
        self._persistence = TokenPersistence(self)

    # -- accessors --------------------------------------------------------
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

    # -- refresh (delegated) ----------------------------------------------
    def ensure_valid(self) -> None:
        self._refresher.ensure_valid()

    def try_refresh_on_401(self) -> bool:
        return self._refresher.try_refresh_on_401()

    def force_refresh(self) -> TokenSnapshot | None:
        return self._refresher.force_refresh()

    def refresh_totp(self) -> TokenSnapshot:
        return self._refresher.refresh_totp()

    # -- bootstrap ---------------------------------------------------------
    def bootstrap(self) -> TokenSnapshot:
        """Acquire the initial state from settings or the persisted JSON file."""
        with self._lock:
            if self._settings.is_totp:
                return self._refresher._bootstrap_totp_if_needed()

            if self._state_store is not None:
                persisted = self._state_store.load()
                if persisted and self._persistence.valid_persisted(persisted):
                    state = self._persistence.from_persisted(persisted)
                    with self._lock:
                        self._state = state
                        self._holder.replace(
                            UpstoxStaticTokenHolder(
                                state.access_token,
                                analytics_only=False,
                                label="Upstox token (persisted)",
                            )
                        )
                    return state
            return self._persistence.acquire_initial()

    # -- interactive OAuth / webhook (delegated) ---------------------------
    def perform_interactive_oauth(
        self,
        pkce_pair: PkcePair | None = None,
        redirect_uri: str | None = None,
        browser_opener: any | None = None,
    ) -> PkcePair:
        return self._oauth.perform_interactive(pkce_pair, redirect_uri, browser_opener)

    def complete_interactive_oauth(
        self, code: str, pkce_pair: PkcePair, redirect_uri: str | None = None
    ) -> TokenSnapshot:
        return self._oauth.complete_interactive(code, pkce_pair, redirect_uri)

    def upgrade_from_webhook(self, access_token: str, expires_at_ms: int) -> bool:
        return self._oauth.upgrade_from_webhook(access_token, expires_at_ms)

    # -- invalidation (delegated) ------------------------------------------
    def invalidate(self, access_token: str | None = None) -> bool:
        return self._persistence.invalidate(access_token)

    # -- holder factory classmethods --------------------------------------
    @classmethod
    def create_extended(cls, extended_token: str) -> UpstoxExtendedTokenHolder:
        return TokenHolderFactory().extended(extended_token)

    @classmethod
    def create_analytics(cls, analytics_token: str) -> UpstoxAnalyticsTokenHolder:
        return TokenHolderFactory().analytics(analytics_token)

    @classmethod
    def create_static(cls, access_token: str) -> UpstoxStaticTokenHolder:
        return TokenHolderFactory().static(access_token)

    # -- private primitives (kept for test monkey-patching) ---------------
    def _build_initial_holder(self) -> UpstoxTokenHolder:
        return self._factory.build_initial(self._settings)

    def _needs_proactive_refresh(self) -> bool:
        return self._refresher._needs_proactive_refresh()

    def _effective_expiry_ms(self) -> int:
        return self._refresher._effective_expiry_ms()

    def _run_exclusive_refresh(
        self, action: Callable[[], TokenSnapshot]
    ) -> TokenSnapshot | None:
        return self._refresher._run_exclusive_refresh(action)

    def _do_totp_refresh(self) -> TokenSnapshot:
        return self._refresher._do_totp_refresh()

    def _do_totp_force_refresh(self) -> TokenSnapshot:
        return self._refresher._do_totp_force_refresh()

    def _do_oauth_refresh(self) -> TokenSnapshot:
        return self._refresher._do_oauth_refresh()

    def _apply_token_state(self, state: TokenSnapshot, *, label: str) -> TokenSnapshot:
        return self._refresher._apply_token_state(state, label=label)

    def _bootstrap_totp_if_needed(self) -> TokenSnapshot:
        return self._refresher._bootstrap_totp_if_needed()

    def _acquire_initial(self) -> TokenSnapshot:
        return self._persistence.acquire_initial()

    def _refresh_now(self) -> None:
        self._persistence.refresh_now()

    def _persist(self, state: TokenSnapshot) -> None:
        self._persistence.persist(state)

    def _valid_persisted(self, persisted: dict) -> bool:
        return self._persistence.valid_persisted(persisted)

    def _valid_snapshot(self, state: TokenSnapshot) -> bool:
        return self._persistence.valid_snapshot(state)

    def _from_persisted(self, persisted: dict) -> TokenSnapshot:
        return self._persistence.from_persisted(persisted)

    def _bootstrap_totp(self) -> TokenSnapshot:
        return self._persistence.bootstrap_totp()
