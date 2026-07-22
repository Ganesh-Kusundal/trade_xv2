"""Runtime execution-target configuration (ADR-0012 / ADR-0013 R15 prep)."""

from __future__ import annotations

import os

from domain.ports.execution_target import ExecutionTargetKind

_DEFAULT = ExecutionTargetKind.PAPER

# ADR-0013 documented thresholds (lift blocked until met).
_LIVE_PREDEPLOY_MIN = 8.5
_CHAOS_STREAK_REQUIRED = 4
_DEFAULT_LIVE_PREDEPLOY_SCORE = 6.8  # ponytail: ADR-0013 baseline until re-score


def _live_predeploy_score() -> float:
    return float(os.getenv("TRADEX_LIVE_PREDEPLOY_SCORE", str(_DEFAULT_LIVE_PREDEPLOY_SCORE)))


def _chaos_green_streak() -> int:
    raw = os.getenv("TRADEX_CHAOS_GREEN_STREAK", "0")
    return int(raw)


def requested_live_execution_target() -> bool:
    """True when config/env explicitly requests LIVE (not the paper default)."""
    raw = os.getenv("TRADEX_EXECUTION_TARGET", _DEFAULT.value)
    try:
        return ExecutionTargetKind.from_str(raw) is ExecutionTargetKind.LIVE
    except ValueError:
        return False


def assert_live_lift_preconditions() -> None:
    """Fail-closed ADR-0013 live lift gate — prep seam; does not enable live alone.

    Requires double opt-in (``TRADEX_ENABLE_LIVE_EXECUTION=1`` **and**
    ``TRADEX_ADR_0013_LIFT=1``) plus operational gates (PRE-DEPLOY score,
    chaos streak). Flags without gates still raise.
    """
    violations: list[str] = []

    if os.getenv("TRADEX_ENABLE_LIVE_EXECUTION", "0") != "1":
        violations.append(
            "TRADEX_ENABLE_LIVE_EXECUTION=1 required for live execution target"
        )
    if os.getenv("TRADEX_ADR_0013_LIFT", "0") != "1":
        violations.append(
            "TRADEX_ADR_0013_LIFT=1 required (ADR-0013 double opt-in; "
            "TRADEX_ENABLE_LIVE_EXECUTION alone is insufficient)"
        )

    score = _live_predeploy_score()
    if score < _LIVE_PREDEPLOY_MIN:
        violations.append(
            f"Live PRE-DEPLOY score {score} < {_LIVE_PREDEPLOY_MIN} (ADR-0013 gate 2)"
        )

    streak = _chaos_green_streak()
    if streak < _CHAOS_STREAK_REQUIRED:
        violations.append(
            f"Weekly chaos green streak {streak}/{_CHAOS_STREAK_REQUIRED} "
            "(ADR-0013 gate 3)"
        )

    if violations:
        raise RuntimeError(
            "Live execution lift preconditions not met (ADR-0013):\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


def resolve_execution_target_kind(
    explicit: ExecutionTargetKind | str | None = None,
) -> ExecutionTargetKind:
    """Resolve the active execution target for this process.

    Defaults to PAPER. LIVE is rejected until ADR-0013 lift gates pass.
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
        assert_live_lift_preconditions()
        return kind
    return kind


def is_live_execution_target() -> bool:
    """True when the resolved process execution target is LIVE."""
    return resolve_execution_target_kind() is ExecutionTargetKind.LIVE


__all__ = [
    "assert_live_lift_preconditions",
    "is_live_execution_target",
    "requested_live_execution_target",
    "resolve_execution_target_kind",
]
