"""Authenticated broker readiness probes — real API calls before live trading."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from infrastructure.auth.credential_resolver import CredentialResolver

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthProbeResult:
    """Outcome of an authenticated readiness probe."""

    ok: bool
    probe_name: str | None = None
    error: str | None = None
    token_rejected: bool = False
    refreshed_token: bool = False


def is_token_rejection(exc: BaseException) -> bool:
    """Return True when *exc* indicates broker rejected the access token."""
    name = type(exc).__name__
    if name in ("AuthenticationError", "UpstoxAuthError"):
        return True
    msg = str(exc).lower()
    if "401" in msg or "403" in msg:
        return True
    if "dh-906" in msg or "dh-808" in msg:
        return True
    if "invalid token" in msg or "token rejected" in msg:
        return True
    return bool("unauthorized" in msg or "forbidden" in msg)


def is_funds_maintenance(exc: BaseException) -> bool:
    """Return True when *exc* is Upstox overnight funds maintenance (HTTP 423)."""
    name = type(exc).__name__
    if name == "UpstoxFundsMaintenanceError":
        return True
    status = getattr(exc, "status_code", None)
    if status == 423:
        return True
    msg = str(exc).lower()
    return "423" in msg or ("locked" in msg and "maintenance" in msg)


def _upstox_market_status_ok(oauth_client: Any, token: str) -> bool:
    return bool(oauth_client.validate_read_only_token(token))


def _probe_upstox(gateway: Any) -> AuthProbeResult:
    broker_obj = getattr(gateway, "_broker", None)
    probe_name = "upstox.profile"
    token: str | None = None
    oauth_client: Any | None = None

    if broker_obj is not None:
        tm = getattr(broker_obj, "token_manager", None)
        if tm is not None and hasattr(tm, "oauth_client"):
            oauth_client = tm.oauth_client
            try:
                token = tm.bearer_token()
                if not token:
                    return AuthProbeResult(
                        ok=False,
                        probe_name=probe_name,
                        error="Upstox bearer token is empty",
                        token_rejected=True,
                    )
                exp_ms = oauth_client.fetch_profile(token)
                now_ms = int(time.time() * 1000)
                if exp_ms > now_ms:
                    return AuthProbeResult(ok=True, probe_name=probe_name)
                if exp_ms == 0:
                    return AuthProbeResult(ok=True, probe_name=probe_name)
                if exp_ms > 0:
                    return AuthProbeResult(
                        ok=False,
                        probe_name=probe_name,
                        error="Upstox token expired (profile token_expiry in past)",
                        token_rejected=True,
                    )
                if _upstox_market_status_ok(oauth_client, token):
                    return AuthProbeResult(
                        ok=True,
                        probe_name="upstox.profile_or_market_status",
                    )
            except Exception as exc:
                rejected = is_token_rejection(exc)
                return AuthProbeResult(
                    ok=False,
                    probe_name=probe_name,
                    error=str(exc),
                    token_rejected=rejected,
                )

    probe_name = "upstox.funds"
    try:
        gateway.funds()
        return AuthProbeResult(ok=True, probe_name=probe_name)
    except Exception as exc:
        if is_funds_maintenance(exc) and oauth_client is not None and token:
            if _upstox_market_status_ok(oauth_client, token):
                return AuthProbeResult(
                    ok=True,
                    probe_name="upstox.profile_or_market_status",
                )
            return AuthProbeResult(
                ok=False,
                probe_name=probe_name,
                error=str(exc),
                token_rejected=False,
            )
        rejected = is_token_rejection(exc)
        return AuthProbeResult(
            ok=False,
            probe_name=probe_name,
            error=str(exc),
            token_rejected=rejected,
        )


def execute_read_only_probe(gateway: Any, broker: str) -> AuthProbeResult:
    """Perform a single read-only authenticated API call."""
    from infrastructure.auth.metrics import AuthMetrics
    from infrastructure.broker_plugin import ensure_core_plugins, get_broker_plugin

    broker = broker.lower().strip()
    ensure_core_plugins()
    plugin = get_broker_plugin(broker)
    if plugin is None or not plugin.is_live:
        AuthMetrics.probe_ok(broker)
        return AuthProbeResult(ok=True, probe_name=f"{broker}_skip")

    handler = _PROBE_DISPATCH.get(broker)
    if handler is None:
        AuthMetrics.probe_fail(broker)
        return AuthProbeResult(ok=False, error=f"unsupported broker: {broker}")
    result = handler(gateway)
    if result.ok:
        AuthMetrics.probe_ok(broker)
    else:
        AuthMetrics.probe_fail(broker)
        if result.token_rejected:
            AuthMetrics.token_rejected(broker)
    return result


def authenticated_readiness_probe(
    gateway: Any,
    broker: str,
    env_path: str | Path | None = None,
) -> AuthProbeResult:
    """Probe broker API auth; on token rejection force one refresh and retry."""
    from infrastructure.broker_plugin import ensure_core_plugins, get_broker_plugin

    broker = broker.lower().strip()
    ensure_core_plugins()
    plugin = get_broker_plugin(broker)
    if plugin is not None and not plugin.is_live:
        return AuthProbeResult(ok=True, probe_name=f"{broker}_skip")

    first = execute_read_only_probe(gateway, broker)
    if first.ok:
        return first

    if not first.token_rejected and not is_token_rejection_from_result(first):
        return first

    logger.info(
        "authenticated_probe_token_rejected",
        extra={"broker": broker, "probe": first.probe_name},
    )
    try:
        refreshed = _force_token_refresh(gateway, broker, env_path=env_path)
        refresh_error: str | None = None
    except Exception as remint_exc:
        refreshed = False
        refresh_error = str(remint_exc)
        logger.warning(
            "authenticated_probe_remint_exception",
            extra={"broker": broker, "error": refresh_error},
        )
    if not refreshed:
        detail = first.error or "token rejected"
        if refresh_error:
            detail = f"{detail}; auto remint failed: {refresh_error}"
        else:
            detail = f"{detail}; auto remint failed (TOTP/credentials/cooldown)"
        return AuthProbeResult(
            ok=False,
            probe_name=first.probe_name,
            error=detail,
            token_rejected=True,
            refreshed_token=False,
        )

    second = execute_read_only_probe(gateway, broker)
    if second.ok:
        return AuthProbeResult(
            ok=True,
            probe_name=second.probe_name,
            token_rejected=True,
            refreshed_token=True,
        )
    return AuthProbeResult(
        ok=False,
        probe_name=second.probe_name,
        error=second.error or "authenticated probe failed after token refresh",
        token_rejected=True,
        refreshed_token=True,
    )


def is_token_rejection_from_result(result: AuthProbeResult) -> bool:
    return result.token_rejected


def _probe_dhan(gateway: Any) -> AuthProbeResult:
    probe_name = "dhan.funds"
    try:
        gateway.funds()
        return AuthProbeResult(ok=True, probe_name=probe_name)
    except Exception as exc:
        rejected = is_token_rejection(exc)
        return AuthProbeResult(
            ok=False,
            probe_name=probe_name,
            error=str(exc),
            token_rejected=rejected,
        )


_PROBE_DISPATCH: dict[str, Any] = {
    "paper": lambda gw: AuthProbeResult(ok=True, probe_name="paper_skip"),
    "dhan": _probe_dhan,
    "upstox": _probe_upstox,
}


_REFRESH_DISPATCH: dict[str, Any] = {
    "dhan": lambda gw, ep: _force_dhan_token_refresh(gw, env_path=ep),
    "upstox": lambda gw, ep: _force_upstox_token_refresh(gw),
}

_SKIP_AUTH_PROBE: set[str] = {"paper"}


def _force_token_refresh(
    gateway: Any,
    broker: str,
    env_path: str | Path | None = None,
) -> bool:
    broker = broker.lower().strip()
    handler = _REFRESH_DISPATCH.get(broker)
    if handler is not None:
        return handler(gateway, env_path)
    return False


def _resolve_dhan_env_path(env_path: str | Path | None) -> Path:
    resolved = CredentialResolver.resolve_env_path("dhan", env_path)
    return resolved if resolved is not None else Path(".env.local")


def _force_dhan_token_refresh(
    gateway: Any,
    env_path: str | Path | None = None,
) -> bool:
    """Remint Dhan token after 401 and push it into client + receivers.

    Factory wires ``connection._auth`` as :class:`AuthManager` with
    ``on_refresh`` → TOTP mint. We revoke first so a rejected JWT cannot
    be reloaded from the store by a subsequent ``acquire()``.
    """
    conn = getattr(gateway, "_conn", None)
    if conn is None:
        return False
    auth = getattr(conn, "_auth", None)
    client = getattr(conn, "_client", None)
    if auth is None:
        logger.warning("dhan_force_token_refresh_failed: connection has no _auth")
        return False
    try:
        # Drop rejected token so force_refresh/on_refresh is the only path.
        revoke = getattr(auth, "revoke", None)
        if callable(revoke):
            revoke()
        state = auth.force_refresh()
        if not state or not state.access_token:
            return False
        if client is not None:
            client.update_token(state.access_token)
        if hasattr(conn, "broadcast_token"):
            conn.broadcast_token(state.access_token)
        try:
            from infrastructure.auth.token_persistence import TokenPersistence

            dhan_env = _resolve_dhan_env_path(env_path)
            store = getattr(auth, "_store", None)
            if store is not None:
                TokenPersistence.save(
                    state,
                    store,
                    dhan_env if dhan_env.exists() else None,
                    env_key="DHAN_ACCESS_TOKEN",
                )
        except Exception as exc:
            logger.debug("dhan_env_token_update_skipped: %s", exc)
        return True
    except Exception as exc:
        logger.warning("dhan_force_token_refresh_failed: %s", exc)
        return False


def _force_upstox_token_refresh(gateway: Any) -> bool:
    broker_obj = getattr(gateway, "_broker", None)
    if broker_obj is None:
        return False
    tm = getattr(broker_obj, "token_manager", None)
    if tm is None:
        return False
    settings = getattr(tm, "settings", None) or getattr(broker_obj, "settings", None)
    try:
        if settings is not None and getattr(settings, "is_totp", False):
            tm.refresh_totp()
        elif settings is not None and getattr(settings, "has_refresh", False):
            tm.force_refresh()
        else:
            return False
        return bool(tm.current_token())
    except Exception as exc:
        logger.warning("upstox_force_token_refresh_failed: %s", exc)
        return False


__all__ = [
    "AuthProbeResult",
    "authenticated_readiness_probe",
    "execute_read_only_probe",
    "is_token_rejection",
    "is_token_rejection_from_result",
]
