"""API process session lifecycle (ADR-0020).

Single process-wide session holder wired once at ``create_app`` / API bootstrap.
Order routes use the registered ``ExecutionComposer`` + OMS — not per-request
``tradex.connect()``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


@dataclass
class ApiProcessSession:
    """Process singleton: trading runtime wired at API startup."""

    trading_context: Any | None = None
    execution_composer: Any | None = None
    runtime: Any | None = None


_session: ApiProcessSession | None = None


def build_trading_context(*, event_bus: Any) -> Any:
    """Build a TradingContext when ``create_app`` receives ``event_bus`` only."""
    from application.oms.factory import create_trading_context

    return create_trading_context(event_bus=event_bus)


def wire_api_process_session(
    *,
    trading_context: Any | None = None,
    execution_composer: Any | None = None,
    runtime: Any | None = None,
) -> None:
    """Register the process session once (idempotent)."""
    global _session
    if _session is not None:
        logger.warning("ApiProcessSession already wired — ignoring duplicate")
        return
    _session = ApiProcessSession(
        trading_context=trading_context,
        execution_composer=execution_composer,
        runtime=runtime,
    )
    logger.info(
        "ApiProcessSession wired (trading_context=%s, execution_composer=%s)",
        "yes" if trading_context else "no",
        "yes" if execution_composer else "no",
    )


def get_api_process_session() -> ApiProcessSession:
    """Return the wired process session or raise HTTP 503."""
    if _session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "API process session not wired — server startup did not complete. "
                "Check logs for bootstrap errors."
            ),
        )
    return _session


def reset_api_process_session() -> None:
    """Clear the process session. FOR TESTING ONLY."""
    global _session
    _session = None


__all__ = [
    "ApiProcessSession",
    "build_trading_context",
    "get_api_process_session",
    "reset_api_process_session",
    "wire_api_process_session",
]
