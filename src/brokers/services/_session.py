"""Shared session helpers — low-level BrokerSession open/borrow/status utilities.

These are the building blocks reused by every other service module. Kept free
of cross-imports into the higher-level service modules to avoid cycles; the one
dependency on :func:`format_session_capabilities` is imported lazily inside
:func:`extensions_from_session`.
"""

from __future__ import annotations

from typing import Any

from brokers.session import BrokerSession


def _open(broker: str, **kwargs: Any) -> BrokerSession:
    return BrokerSession(broker, **kwargs)


def _borrow_session(
    broker: str,
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> tuple[BrokerSession, bool]:
    """Return ``(session, should_close)``. Reuse *session* when the shell holds one open."""
    if session is not None:
        return session, False
    return _open(broker, **kwargs), True


def status_from_session(session: BrokerSession) -> dict[str, Any]:
    """Status dict from an already-open session (no reconnect)."""
    st = session.status
    checkpoints = [
        {"name": c.name, "ok": c.ok, "detail": c.detail}
        for c in getattr(session.runtime, "checkpoints", [])
    ]
    return {
        "broker_id": session.broker_id,
        "mode": getattr(st, "mode", None),
        "orders_enabled": getattr(st, "orders_enabled", None),
        "authenticated": getattr(st, "authenticated", None),
        "instruments_loaded": getattr(st, "instruments_loaded", None),
        "checkpoints": checkpoints,
        "connected": True,
    }


def extensions_from_session(session: BrokerSession, symbol: str = "RELIANCE") -> list[str]:
    from .capabilities import format_session_capabilities

    try:
        return list(format_session_capabilities(session, symbol).get("extensions") or [])
    except Exception:
        return []


def run_connect(
    broker: str = "paper",
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Connect and return status + startup checkpoints (Trading OS startup flow)."""
    if session is not None:
        return status_from_session(session)
    s = _open(broker, **kwargs)
    try:
        return status_from_session(s)
    finally:
        s.close()


__all__ = [
    "_open",
    "_borrow_session",
    "status_from_session",
    "extensions_from_session",
    "run_connect",
]
