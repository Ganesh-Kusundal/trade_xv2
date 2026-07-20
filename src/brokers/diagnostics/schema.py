"""Doctor JSON schema — unified across SDK, CLI, MCP (TRANS-P4-002 / ADR-019)."""

from __future__ import annotations

from typing import Any, Literal

from brokers.certification.market_hours import is_nse_market_open
from brokers.diagnostics.core import CheckResult, CheckStatus

DOCTOR_SCHEMA_VERSION = 1
GateStatus = Literal["passed", "failed", "blocked"]


def check_status_to_gate(status: CheckStatus) -> GateStatus:
    if status == CheckStatus.PASS:
        return "passed"
    if status == CheckStatus.FAIL:
        return "failed"
    return "blocked"


def resolve_overall(checks: list[CheckResult]) -> GateStatus:
    if any(c.status == CheckStatus.FAIL for c in checks):
        return "failed"
    if any(c.status in (CheckStatus.WARNING, CheckStatus.SKIP) for c in checks):
        return "blocked"
    return "passed"


def format_check(check: CheckResult) -> dict[str, Any]:
    return {
        "id": check.name,
        "status": check_status_to_gate(check.status),
        "message": check.detail,
        "latency_ms": check.latency_ms,
    }


def format_doctor_dict(
    *,
    broker_id: str,
    checks: list[CheckResult],
    command: str = "doctor",
    mode: str | None = None,
    live: bool = False,
) -> dict[str, Any]:
    """Build the canonical doctor JSON payload."""
    return {
        "schema_version": DOCTOR_SCHEMA_VERSION,
        "command": command,
        "broker": broker_id,
        "mode": mode,
        "overall": resolve_overall(checks),
        "checks": [format_check(c) for c in checks],
        "environment": {
            "live": live,
            "market_hours": is_nse_market_open(),
        },
    }
