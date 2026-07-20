"""Runtime execution-target configuration (ADR-0012)."""

from __future__ import annotations

import os

from domain.ports.execution_target import ExecutionTargetKind

_DEFAULT = ExecutionTargetKind.PAPER


def resolve_execution_target_kind(
    explicit: ExecutionTargetKind | str | None = None,
) -> ExecutionTargetKind:
    """Resolve the active execution target for this process.

    Defaults to PAPER. LIVE is rejected until a future execution plugin is wired.
    """
    if explicit is not None:
        kind = (
            ExecutionTargetKind.from_str(explicit)
            if isinstance(explicit, str)
            else explicit
        )
    else:
        raw = os.getenv("TRADEX_EXECUTION_TARGET", _DEFAULT.value)
        kind = ExecutionTargetKind.from_str(raw)

    if kind is ExecutionTargetKind.LIVE:
        raise RuntimeError(
            "Live execution is disabled. Product scope is paper-only; "
            "set TRADEX_EXECUTION_TARGET=paper (default)."
        )
    return kind


__all__ = ["resolve_execution_target_kind"]
