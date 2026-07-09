"""Single production composition helpers for the OMS (ENG-011).

Canonical process wiring:

1. Composition root (CLI ``oms_setup`` / FastAPI ``create_app``) builds a
   :class:`~application.oms.context.TradingContext` with durable store,
   EventLog, risk capital, and bus.
2. Root calls :func:`register_process_oms`.
3. ``tradex.connect`` / Session.buy resolve that book via
   :func:`application.oms.session_bridge.build_oms_service`.

There is one money book per process when the root has run. Standalone paper
may build an in-memory OMS. Live brokers without a registered context are
refused (ENG-001).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from application.oms.process_context import (
    get_oms_context,
    has_oms_context,
    register_oms_context,
    reset_oms_context,
)

if TYPE_CHECKING:
    from application.oms.context import TradingContext

__all__ = [
    "get_oms_context",
    "has_oms_context",
    "register_process_oms",
    "require_process_oms",
    "reset_oms_context",
]


def register_process_oms(ctx: "TradingContext") -> None:
    """Register the process-wide OMS (alias of :func:`register_oms_context`)."""
    register_oms_context(ctx)


def require_process_oms(*, for_broker: str | None = None) -> "TradingContext":
    """Return the registered TradingContext or raise with operator guidance.

    Parameters
    ----------
    for_broker:
        Optional broker id included in the error message.
    """
    if not has_oms_context():
        broker = for_broker or "live"
        raise RuntimeError(
            f"No process OMS registered for broker={broker!r}. "
            "Start via CLI BrokerService / FastAPI create_app so "
            "register_process_oms(TradingContext) runs before trading. "
            "(ENG-011 single composition root)"
        )
    ctx = get_oms_context()
    if ctx is None:
        raise RuntimeError("OMS context flag set but context is None")
    return ctx
