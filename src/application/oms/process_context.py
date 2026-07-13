"""Process-wide OMS singleton registry.

Consolidates the three competing order-management stacks (tradex.connect's
ephemeral OMS, the DI-backed TradingContext, and the ExecutionComposer bypass)
into ONE canonical, bus-wired TradingContext per process.

The composition root (CLI BrokerService, FastAPI create_app) builds the
TradingContext and registers it here via :func:`register_oms_context`. Every
entry point that places/reads orders — ``tradex.connect``/``Session.buy``,
the REST API, the CLI — MUST resolve the same instance via
:func:`get_oms_context`. This guarantees fills land in the order book the
operator later queries, and that kill-switch / idempotency are process-wide.

A fresh process that has not registered a context: paper/SDK may build an
in-memory OMS via ``build_oms_service`` (ENG-001). Live brokers refuse that
path unless ``allow_unsafe_standalone=True``. Prefer registering a full
``TradingContext`` from CLI/API composition roots.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from application.oms.context import TradingContext

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_registered: "TradingContext | None" = None


def register_oms_context(ctx: "TradingContext") -> None:
    """Register the canonical process-wide OMS context.

    Called by the composition root (CLI BrokerService.register_oms_services,
    FastAPI create_app via initialize_all_services). Idempotent: calling
    again with the same instance is a no-op; calling with a different
    instance logs a warning (double composition root) and keeps the first.
    """
    global _registered  # intentional module singleton — process-wide OMS context
    with _lock:
        if _registered is not None and _registered is not ctx:
            logger.warning(
                "OMS context already registered; ignoring second registration. "
                "Multiple composition roots in one process corrupt order state."
            )
            return
        _registered = ctx


def get_oms_context() -> "TradingContext | None":
    """Return the registered process-wide OMS context, or None if not set."""
    with _lock:
        return _registered


def has_oms_context() -> bool:
    with _lock:
        return _registered is not None


def reset_oms_context() -> None:
    """FOR TESTS ONLY. Drop the registered context."""
    global _registered  # intentional module singleton — reset for tests
    with _lock:
        _registered = None
