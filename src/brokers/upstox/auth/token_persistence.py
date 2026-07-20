"""Token persistence, invalidation, and bootstrap helpers for ``UpstoxTokenManager``.

Extracted from ``UpstoxTokenManager`` so state persistence and the initial
acquisition logic are isolated from refresh orchestration.
"""

from __future__ import annotations

import logging
import os
import sys
import time

from domain.constants import SECONDS_PER_DAY
from infrastructure.auth.jwt_expiry import JwtExpiry

from .exceptions import UpstoxAuthError
from .holders import TokenSnapshot, UpstoxStaticTokenHolder
from .token_expiry import UpstoxTokenExpiry

try:
    from .totp_client import UpstoxTotpClient
except Exception:  # pragma: no cover - totp_client imports optional deps lazily
    UpstoxTotpClient = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class TokenPersistence:
    """Invalidation, initial acquisition, refresh, and JSON persistence."""

    def __init__(self, manager: any) -> None:
        self._m = manager

    def invalidate(self, access_token: str | None = None) -> bool:
        """Reject ad-hoc invalidation if a fresher token already exists.

        Mirrors Trade_J ``TokenLifecycleService.invalidate`` policy.
        """
        m = self._m
        with m._lock:
            current = m._state
            if current is None:
                return True
            if access_token and access_token != current.access_token:
                logger.debug(
                    "invalidate ignored — current token does not match supplied access_token"
                )
                return False
            now_ms = int(time.time() * 1000)
            return not (current.expires_at_ms and current.expires_at_ms > now_ms)

    def acquire_initial(self) -> TokenSnapshot:
        m = self._m
        s = m._settings
        if s.access_token:
            if s.refresh_token:
                exp = m._oauth_client.fetch_profile(s.access_token)
                if exp <= 0:
                    exp = JwtExpiry.parse_expiry_epoch_ms(s.access_token)
                if exp <= 0:
                    exp = UpstoxTokenExpiry.next_expiry_epoch_ms()
                state = TokenSnapshot(
                    access_token=s.access_token,
                    refresh_token=s.refresh_token,
                    expires_at_ms=exp,
                    issued_at_ms=int(time.time() * 1000),
                    source="OAUTH",
                )
                with m._lock:
                    m._state = state
                    m._holder.replace(
                        UpstoxStaticTokenHolder(
                            s.access_token, analytics_only=False, label="Upstox token (bootstrap)"
                        )
                    )
                    self._m._persist(state)
                return state
            jwt_exp = JwtExpiry.parse_expiry_epoch_ms(s.access_token)
            exp = jwt_exp if jwt_exp > 0 else UpstoxTokenExpiry.next_expiry_epoch_ms()
            state = TokenSnapshot(
                access_token=s.access_token,
                refresh_token=None,
                expires_at_ms=exp,
                issued_at_ms=int(time.time() * 1000),
                source="STATIC",
            )
            with m._lock:
                m._state = state
                m._holder.replace(
                    UpstoxStaticTokenHolder(
                        s.access_token, analytics_only=False, label="Upstox token"
                    )
                )
                self._m._persist(state)
            return state
        raise UpstoxAuthError(
            "No Upstox access token available. Paste UPSTOX_ACCESS_TOKEN in env or run "
            "performInteractiveOAuth()."
        )

    def refresh_now(self) -> None:
        m = self._m
        state = m._state
        if state is None or not state.refresh_token:
            raise UpstoxAuthError("Cannot refresh token: no refresh token available")
        resp = m._oauth_client.refresh_token(
            refresh_token=state.refresh_token,
            client_id=m._settings.client_id,
            client_secret=m._settings.client_secret,
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
                    new_state.access_token, analytics_only=False, label="Upstox token (refreshed)"
                )
            )
            self._m._persist(new_state)

    def persist(self, state: TokenSnapshot) -> None:
        m = self._m
        if m._state_store is None:
            return
        try:
            m._state_store.save(
                {
                    "access_token": state.access_token,
                    "refresh_token": state.refresh_token,
                    "expires_at_ms": state.expires_at_ms,
                    "issued_at_ms": state.issued_at_ms,
                    "source": state.source,
                }
            )
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("Failed to persist Upstox token state: %s", exc)

    def valid_persisted(self, persisted: dict) -> bool:
        if not isinstance(persisted, dict):
            return False
        token = persisted.get("access_token")
        if not token or not isinstance(token, str):
            return False
        exp = int(persisted.get("expires_at_ms", 0) or 0)
        return exp > int(time.time() * 1000)

    def valid_snapshot(self, state: TokenSnapshot) -> bool:
        if not state.access_token:
            return False
        exp = int(state.expires_at_ms or 0)
        if exp <= 0:
            return False
        return exp > int(time.time() * 1000)

    def from_persisted(self, persisted: dict) -> TokenSnapshot:
        return TokenSnapshot(
            access_token=persisted["access_token"],
            refresh_token=persisted.get("refresh_token"),
            expires_at_ms=int(persisted.get("expires_at_ms", 0)),
            issued_at_ms=int(persisted.get("issued_at_ms", 0)),
            source=str(persisted.get("source", "OAUTH")),
        )

    def bootstrap_totp(self) -> TokenSnapshot:
        """Bootstrap token using TOTP auto-generation.

        Generates a fresh token using the upstox-totp library and persists it.
        Falls back to refresh-token mechanism if TOTP generation fails.
        """
        m = self._m
        try:
            logger.info("Attempting TOTP token generation...")
            totp_client = UpstoxTotpClient(m._settings)

            if not totp_client.validate_config():
                raise UpstoxAuthError(
                    "TOTP configuration incomplete. Set UPSTOX_MOBILE, UPSTOX_PIN, "
                    "and UPSTOX_TOTP_SECRET environment variables."
                )

            result = totp_client.generate_token()
            access_token = result["access_token"]

            # Parse expiry from JWT.
            exp = JwtExpiry.parse_expiry_epoch_ms(access_token)
            if exp <= 0:
                exp = UpstoxTokenExpiry.next_expiry_epoch_ms()

            state = TokenSnapshot(
                access_token=access_token,
                refresh_token=None,  # TOTP tokens don't have refresh tokens
                expires_at_ms=exp,
                issued_at_ms=int(time.time() * 1000),
                source="TOTP",
            )

            self._m._apply_token_state(state, label="Upstox token (TOTP)")
            logger.info("TOTP token bootstrap successful, expires at: %d", exp)
            return state

        except Exception as exc:
            logger.warning("TOTP bootstrap failed: %s", exc)

            # Fallback to interactive browser OAuth login on local machine if not disabled and not in tests.
            in_test = "pytest" in sys.modules or "unittest" in sys.modules
            if os.getenv("UPSTOX_DISABLE_INTERACTIVE_FALLBACK") != "1" and not in_test:
                logger.warning(
                    "TOTP authentication failed. Falling back to interactive browser login..."
                )
                try:
                    from brokers.upstox.auth.login import perform_login

                    login_result = perform_login(m._settings, timeout=120)
                    expires_in = login_result.get("expires_in_seconds", SECONDS_PER_DAY)
                    issued_at = login_result.get("issued_at_ms", int(time.time() * 1000))

                    state = TokenSnapshot(
                        access_token=login_result["access_token"],
                        refresh_token=login_result.get("refresh_token"),
                        expires_at_ms=issued_at + expires_in * 1000,
                        issued_at_ms=issued_at,
                        source="OAUTH",
                    )
                    self._m._apply_token_state(state, label="Upstox token (interactive fallback)")
                    logger.info("Interactive login fallback successful.")
                    return state
                except Exception as fall_exc:
                    logger.error("Interactive browser login fallback failed: %s", fall_exc)

            # Fallback only to an explicit OAuth refresh token. Do not silently
            # reuse UPSTOX_ACCESS_TOKEN in TOTP mode; stale env tokens mask auth
            # failures as downstream 401s.
            if m._settings.refresh_token:
                logger.info("Falling back to refresh-token mechanism")
                return self.acquire_initial()

            raise UpstoxAuthError(
                f"TOTP authentication failed and no fallback available: {exc}"
            ) from exc
