"""Unified token ensure policy: probe-before-mint, single mint, atomic persist.

Design (from TOTP rate-limit RCA)
---------------------------------
1. Prefer env/store JWT that is still locally valid — never mint.
2. Mint only when missing, expired, or broker_rejected (401/DH-906).
3. Mint at most once per call; mint callback must use TotpCooldownGuard.
4. Persist store + env atomically on every successful mint.
5. API MultiBucket rate limits are unrelated — this module is login/TOTP only.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from infrastructure.auth.metrics import AuthMetrics
from infrastructure.auth.token import TokenSource, TokenState, TokenStateStore
from infrastructure.auth.token_persistence import TokenPersistence, token_state_from_access_token
from infrastructure.auth.token_policy import should_generate_token

logger = logging.getLogger(__name__)


def _broker_from_env_key(env_key: str) -> str:
    key = (env_key or "").upper()
    if key.startswith("DHAN"):
        return "dhan"
    if key.startswith("UPSTOX"):
        return "upstox"
    return "unknown"


def ensure_access_token(
    *,
    store: TokenStateStore,
    env_token: str | None = None,
    mint: Callable[[], str | None],
    env_path: Path | None = None,
    env_key: str = "DHAN_ACCESS_TOKEN",
    broker_rejected: bool = False,
    allow_proactive: bool = False,
    buffer_seconds: float = 0,
    source: TokenSource = TokenSource.TOTP,
    broker: str | None = None,
) -> TokenState | None:
    """Return a usable token state without unnecessary TOTP generation.

    Args:
        store: Persistent JSON (or other) token store.
        env_token: Optional access token from env / settings.
        mint: Zero-arg callable that mints a fresh token (must honor TotpCooldownGuard).
        env_path: Optional env file to mirror the new token into.
        env_key: Env var name for mirror (``DHAN_ACCESS_TOKEN`` / ``UPSTOX_ACCESS_TOKEN``).
        broker_rejected: True when broker returned 401 / DH-906 for current token.
        allow_proactive: If True, mint when within *buffer_seconds* of expiry (OAuth).
        buffer_seconds: Proactive refresh window (ignored unless allow_proactive).
        source: TokenSource for newly minted tokens.

    Returns:
        Valid TokenState, or None if mint failed / was not possible.
    """
    broker_id = (broker or _broker_from_env_key(env_key)).lower()
    state = TokenPersistence.load_canonical(store, env_token)

    if not should_generate_token(
        state,
        broker_rejected=broker_rejected,
        allow_proactive=allow_proactive,
        buffer_seconds=buffer_seconds,
    ):
        logger.debug(
            "token_ensure_reuse",
            extra={
                "env_key": env_key,
                "has_token": bool(state and state.access_token),
                "broker_rejected": broker_rejected,
            },
        )
        AuthMetrics.totp_reuse(broker_id)
        return state

    # Broker rejected a token that may still look valid in JWT — drop store so
    # we cannot reload the same rejected value.
    if broker_rejected:
        AuthMetrics.token_rejected(broker_id)
        try:
            store.save(None)
        except Exception as exc:
            logger.debug("token_ensure_clear_store_failed: %s", exc)

    logger.info(
        "token_ensure_mint",
        extra={
            "env_key": env_key,
            "broker_rejected": broker_rejected,
            "reason": _mint_reason(state, broker_rejected),
        },
    )

    try:
        token = mint()
    except Exception as exc:
        logger.warning(
            "token_ensure_mint_failed",
            extra={"env_key": env_key, "error": str(exc)},
        )
        from infrastructure.auth.totp_cooldown import TotpRateLimitError

        if isinstance(exc, TotpRateLimitError):
            AuthMetrics.totp_rate_limit(broker_id)
        else:
            AuthMetrics.totp_mint_fail(broker_id)
        raise

    if not token:
        logger.warning("token_ensure_mint_empty", extra={"env_key": env_key})
        AuthMetrics.totp_mint_fail(broker_id)
        return None

    new_state = token_state_from_access_token(token, source=source)
    TokenPersistence.save(new_state, store, env_path, env_key=env_key)
    AuthMetrics.totp_mint(broker_id)
    logger.info(
        "token_ensure_mint_ok",
        extra={"env_key": env_key, "expires_at": str(new_state.expires_at)},
    )
    return new_state


def _mint_reason(state: TokenState | None, broker_rejected: bool) -> str:
    if broker_rejected:
        return "broker_rejected"
    if state is None or not state.access_token:
        return "missing"
    if not state.is_valid():
        return "expired"
    return "policy"
