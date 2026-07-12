"""Token refresh orchestration for ``UpstoxTokenManager``.

Holds the proactive-refresh, 401-recovery, force-refresh and TOTP refresh
logic. Cross-cutting primitives (state mutation, persistence, TOTP bootstrap)
are routed back through the owning ``UpstoxTokenManager`` so callers can
monkey-patch those primitives in tests.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from infrastructure.auth.jwt_expiry import JwtExpiry

from .exceptions import UpstoxAuthError
from .holders import TokenSnapshot, UpstoxStaticTokenHolder

logger = logging.getLogger(__name__)

_REFRESH_WAIT_SECONDS = 30.0


class TokenRefresher:
    """Refresh orchestration: proactive, on-401, force, and TOTP."""

    def __init__(self, manager: any) -> None:
        self._m = manager

    # -- public API -------------------------------------------------------
    def ensure_valid(self) -> None:
        m = self._m
        if getattr(m._settings, "analytics_only", False):
            return
        if m._settings.is_extended and m._settings.extended_token:
            return
        if not self._m._needs_proactive_refresh():
            return
        if m._settings.is_totp:
            self._run_exclusive_refresh(self._do_totp_force_refresh)
            return
        with m._lock:
            if m._state and m._state.refresh_token:
                logger.info(
                    "Upstox token at/near expiry; refreshing proactively (expiry=%d)",
                    self._effective_expiry_ms(),
                )
        self._run_exclusive_refresh(self._do_oauth_refresh)

    def try_refresh_on_401(self) -> bool:
        """Refresh token after HTTP 401/403. Returns True if a new token is available.

        TOTP policy (avoids burning login quota):
        1. First 401 for a still-valid JWT → soft-retry once with same token
           (covers transient gateway glitches without TOTP).
        2. Second 401 for the **same** token (or expired JWT) → clear state and
           force **one** mint under TotpCooldownGuard.
        """
        m = self._m
        if getattr(m._settings, "analytics_only", False):
            return False
        try:
            if m._settings.is_totp:
                with m._lock:
                    current = m._state
                    tok = current.access_token if current else None
                    if (
                        current
                        and tok
                        and self._m._valid_snapshot(current)
                        and m._last_401_token != tok
                    ):
                        m._last_401_token = tok
                        logger.info(
                            "Upstox 401 soft-retry: reusing in-memory JWT once (no TOTP)"
                        )
                        return True
                    # Hard path: clear so we cannot reload the rejected JWT.
                    m._state = None
                    m._last_401_token = None
                self._run_exclusive_refresh(self._do_totp_force_refresh)
            elif m._state and m._state.refresh_token:
                self._run_exclusive_refresh(self._do_oauth_refresh)
            else:
                return False
            return bool(self._m.current_token())
        except Exception as exc:
            logger.warning("Upstox token refresh on 401 failed: %s", exc)
            return False

    def force_refresh(self) -> TokenSnapshot | None:
        m = self._m
        if m._settings.is_totp:
            return self._run_exclusive_refresh(self._do_totp_force_refresh)
        with m._lock:
            if not m._state or not m._state.refresh_token:
                raise UpstoxAuthError("Cannot force_refresh: no refresh token available")
        return self._run_exclusive_refresh(self._do_oauth_refresh)

    def refresh_totp(self) -> TokenSnapshot:
        """Regenerate token via TOTP (no refresh_token required)."""
        result = self._run_exclusive_refresh(self._do_totp_force_refresh)
        if result is None:
            raise UpstoxAuthError("TOTP refresh did not produce a token")
        return result

    # -- internal primitives ---------------------------------------------
    def _needs_proactive_refresh(self) -> bool:
        m = self._m
        now_ms = int(time.time() * 1000)
        exp_ms = self._effective_expiry_ms()
        if exp_ms <= 0:
            return m._settings.is_totp
        buffer_ms = int(getattr(m._settings, "refresh_buffer_minutes", 30) or 30) * 60 * 1000
        return now_ms >= exp_ms - buffer_ms

    def _effective_expiry_ms(self) -> int:
        m = self._m
        with m._lock:
            if m._state and m._state.expires_at_ms:
                return int(m._state.expires_at_ms)
            exp = m._holder.expiry_epoch_ms()
            if exp > 0:
                return int(exp)
            token = m._holder.bearer_token() if m._holder else None
        if token:
            return JwtExpiry.parse_expiry_epoch_ms(token)
        return 0

    def _run_exclusive_refresh(
        self, action: Callable[[], TokenSnapshot]
    ) -> TokenSnapshot | None:
        m = self._m
        with m._refresh_lock:
            if m._refresh_done.is_set():
                m._refresh_done.clear()
                leader = True
            else:
                leader = False
        if leader:
            try:
                return action()
            finally:
                m._refresh_done.set()
        if not m._refresh_done.wait(timeout=_REFRESH_WAIT_SECONDS):
            logger.warning("Timed out waiting for in-flight Upstox token refresh")
        with m._lock:
            return m._state

    def _do_totp_refresh(self) -> TokenSnapshot:
        return self._m._bootstrap_totp_if_needed()

    def _do_totp_force_refresh(self) -> TokenSnapshot:
        return self._m._bootstrap_totp()

    def _do_oauth_refresh(self) -> TokenSnapshot:
        self._m._refresh_now()
        with self._m._lock:
            if self._m._state is None:
                raise UpstoxAuthError("OAuth refresh completed without state")
            return self._m._state

    def _apply_token_state(self, state: TokenSnapshot, *, label: str) -> TokenSnapshot:
        m = self._m
        with m._lock:
            m._state = state
            m._holder.replace(
                UpstoxStaticTokenHolder(
                    state.access_token,
                    analytics_only=False,
                    label=label,
                )
            )
            self._m._persist(state)
        return state

    def _bootstrap_totp_if_needed(self) -> TokenSnapshot:
        """Load persisted/env JWT first; generate TOTP only when missing or expired.

        Probe-before-mint: never call upstox-totp when a locally valid JWT exists
        (in-memory, state file, or UPSTOX_ACCESS_TOKEN with valid exp).
        """
        m = self._m
        with m._lock:
            if m._state and self._m._valid_snapshot(m._state):
                logger.debug("Upstox TOTP refresh: reusing in-memory valid token")
                return m._state
        if m._state_store is not None:
            persisted = m._state_store.load()
            if persisted and self._m._valid_persisted(persisted):
                state = self._m._from_persisted(persisted)
                with m._lock:
                    m._state = state
                    m._holder.replace(
                        UpstoxStaticTokenHolder(
                            state.access_token,
                            analytics_only=False,
                            label="Upstox token (persisted TOTP)",
                        )
                    )
                logger.debug("Upstox TOTP bootstrap: reusing persisted token")
                return state

        # Reuse env access token when JWT still valid — avoids burning TOTP.
        env_tok = (getattr(m._settings, "access_token", None) or "").strip()
        if env_tok:
            exp = JwtExpiry.parse_expiry_epoch_ms(env_tok)
            now_ms = int(time.time() * 1000)
            if exp > now_ms:
                state = TokenSnapshot(
                    access_token=env_tok,
                    refresh_token=None,
                    expires_at_ms=exp,
                    issued_at_ms=now_ms,
                    source="TOTP",
                )
                with m._lock:
                    m._state = state
                    m._holder.replace(
                        UpstoxStaticTokenHolder(
                            env_tok,
                            analytics_only=False,
                            label="Upstox token (env JWT still valid)",
                        )
                    )
                    self._m._persist(state)
                logger.info("Upstox TOTP bootstrap: reusing valid env JWT (no mint)")
                return state

        return self._m._bootstrap_totp()
