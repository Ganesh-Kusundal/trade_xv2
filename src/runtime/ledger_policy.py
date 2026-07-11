"""Execution ledger wiring for composition roots (ADR-015).

Pure flag / fail-closed helpers live in ``application.oms.ledger_authority`` so
application code does not import this module (which may pull infrastructure).

Default off until shadow parity proven. Set ``TRADEX_LEDGER_AUTHORITY=1`` to
wire ``SqliteExecutionLedger`` at composition roots.
"""

from __future__ import annotations

import logging
from typing import Any

from application.oms.ledger_authority import (
    ledger_authority_enabled,
    require_execution_ledger,
)

logger = logging.getLogger(__name__)

_ENV_LEDGER_AUTHORITY = "TRADEX_LEDGER_AUTHORITY"

__all__ = [
    "ledger_authority_enabled",
    "require_execution_ledger",
    "resolve_execution_ledger",
]


def resolve_execution_ledger(
    *,
    builder: Any | None = None,
    db_path: str | None = None,
) -> Any | None:
    """Build execution ledger when authority flag is on; otherwise None."""
    if not ledger_authority_enabled():
        return None
    if builder is None:
        from infrastructure.bootstrap import build_execution_ledger

        builder = build_execution_ledger
    try:
        ledger = builder(db_path) if db_path else builder()
        logger.info("execution_ledger_enabled env=%s", _ENV_LEDGER_AUTHORITY)
        return ledger
    except Exception as exc:
        logger.error("execution_ledger_build_failed: %s", exc)
        raise RuntimeError(
            f"{_ENV_LEDGER_AUTHORITY}=1 requires a working execution ledger"
        ) from exc
