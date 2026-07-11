"""Pure execution-ledger authority policy (ADR-015) — no infrastructure imports.

Composition roots that *build* a ledger still use ``runtime.ledger_policy.resolve_execution_ledger``.
Application/OMS code that only needs the flag or fail-closed check imports from here so
import-linter stays green (application must not transitively import infrastructure).
"""

from __future__ import annotations

import os
from typing import Any

_ENV_LEDGER_AUTHORITY = "TRADEX_LEDGER_AUTHORITY"


def ledger_authority_enabled() -> bool:
    """Return True when durable ledger is the authoritative write boundary."""
    return os.getenv(_ENV_LEDGER_AUTHORITY, "0").strip() == "1"


def require_execution_ledger(ledger: Any | None) -> None:
    """Fail closed when ledger authority is on but no ledger is wired."""
    if ledger_authority_enabled() and ledger is None:
        raise RuntimeError(
            f"{_ENV_LEDGER_AUTHORITY}=1 requires execution ledger at composition root"
        )


__all__ = [
    "ledger_authority_enabled",
    "require_execution_ledger",
]
