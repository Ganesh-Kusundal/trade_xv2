"""Typed bootstrap results — replace silent ``None`` gateway returns.

Re-exports from ``domain.ports.bootstrap`` for backward compatibility.
New code should import from ``domain.ports.bootstrap`` directly.
"""

from __future__ import annotations

import logging
from typing import Any

from domain.ports.bootstrap import (
    BootstrapResult,
    BootstrapStatus,
    classify_exception,
)

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = [
    "BootstrapResult",
    "BootstrapStatus",
    "classify_exception",
    "structural_readiness_probe",
]


def _check_dhan(gateway: Any) -> tuple[bool, str | None]:
    conn = getattr(gateway, "connection", None) or getattr(gateway, "_conn", None)
    if conn is None:
        return False, "gateway missing _conn"
    token = getattr(conn, "access_token", None)
    client = getattr(conn, "_client", None) or getattr(conn, "client", None)
    if not token and client is not None:
        token = getattr(client, "access_token", None)
    if not token:
        auth = getattr(conn, "_auth", None)
        state = getattr(auth, "_state", None) if auth else None
        if state and getattr(state, "access_token", None):
            token = state.access_token
    if not token:
        return False, "no access token on Dhan connection"
    return True, None


def _check_upstox(gateway: Any) -> tuple[bool, str | None]:
    if getattr(gateway, "bootstrap_transport_ready", True) is False:
        return False, "Upstox bootstrap connect failed"
    broker_obj = getattr(gateway, "broker", None) or getattr(gateway, "_broker", None)
    if broker_obj is None:
        return False, "gateway missing _broker"
    tm = getattr(broker_obj, "token_manager", None)
    if tm is not None:
        token = tm.current_token()
        if token and token != "placeholder-totp-will-refresh":
            return True, None
        return False, "Upstox token manager has no valid token"
    settings = getattr(broker_obj, "settings", None)
    if settings and (
        getattr(settings, "access_token", None) or getattr(settings, "analytics_token", None)
    ):
        return True, None
    return False, "no Upstox token in settings or manager"


_STRUCTURAL_CHECKS: dict[str, Any] = {
    "dhan": _check_dhan,
    "upstox": _check_upstox,
    "paper": lambda gw: (True, None),
}


def structural_readiness_probe(gateway: Any, broker: str) -> tuple[bool, str | None]:
    """Lightweight structural check — token present on connection object.

    Does not call broker APIs; verifies the factory wired auth state.
    """
    broker = broker.lower().strip()
    check = _STRUCTURAL_CHECKS.get(broker)
    try:
        if check is not None:
            return check(gateway)
    except Exception as exc:
        return False, str(exc)
    return True, None
