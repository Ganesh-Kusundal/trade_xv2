"""Shared session helpers — low-level BrokerSession open/borrow/status utilities.

These are the building blocks reused by every other service module. Kept free
of cross-imports into the higher-level service modules to avoid cycles; the one
dependency on :func:`format_session_capabilities` is imported lazily inside
:func:`extensions_from_session`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from brokers.session import BrokerSession

logger = logging.getLogger(__name__)

# ── Live-actionable gate (M1: safety spine) ─────────────────────────
# Brokers that require the production readiness gate before order placement.
LIVE_BROKERS: frozenset[str] = frozenset({"dhan", "upstox"})

# Module-level gate callable — set by the composition root (runtime).
# Signature: () -> bool. Returns True when live orders are permitted.
_live_actionable_gate: Callable[[], bool] | None = None


def set_live_actionable_gate(gate: Callable[[], bool] | None) -> None:
    """Register the live-actionable gate from the composition root.

    Called once during startup by the runtime layer. The gate is a simple
    callable that returns ``True`` when the system is ready for live orders.
    """
    global _live_actionable_gate
    _live_actionable_gate = gate
    logger.debug("Live-actionable gate registered: %s", gate is not None)


from domain.exceptions import LiveBrokerBlockedError


def check_live_actionable(broker: str) -> None:
    """Raise ``LiveBrokerBlockedError`` if *broker* is live but the gate blocks.

    Paper and mock brokers are always allowed. Live brokers (dhan, upstox)
    require the gate to return ``True``. If no gate is registered, live
    brokers are **blocked** (fail-closed default — safe with real money).
    """
    if broker.lower() not in LIVE_BROKERS:
        return  # paper / mock — always allowed
    gate = _live_actionable_gate
    if gate is None:
        raise LiveBrokerBlockedError(
            f"OMS refused: no live-actionable gate registered for broker '{broker}'. "
            "Cannot place orders on a live broker without the production readiness gate. "
            "Run `tradex doctor` for the readiness report."
        )
    if not gate():
        raise LiveBrokerBlockedError(
            f"OMS refused: runtime is not live-actionable for broker '{broker}'. "
            "Run `tradex doctor` for the production readiness report; "
            "address every failing check before placing orders."
        )


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
    "LIVE_BROKERS",
    "LiveBrokerBlockedError",
    "_borrow_session",
    "_open",
    "check_live_actionable",
    "extensions_from_session",
    "run_connect",
    "set_live_actionable_gate",
    "status_from_session",
]
