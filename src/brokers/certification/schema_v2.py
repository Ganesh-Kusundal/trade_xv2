"""Certification JSON schema v2 (ADR-018).

Lightweight validation without external jsonschema dependency.
"""

from __future__ import annotations

from typing import Any, Literal

SchemaStatus = Literal["passed", "failed", "blocked"]
CertTier = Literal["L0", "L1", "L2", "L3"]

SCHEMA_VERSION = 2

_VERIFY_REQUIRED = frozenset(
    {"schema_version", "broker_id", "tier", "status", "passed", "certified", "steps"}
)
_CERT_REQUIRED = frozenset(
    {"schema_version", "broker_id", "tier", "status", "is_certified", "passed", "total", "results"}
)
_VALID_STATUS = frozenset({"passed", "failed", "blocked"})
_VALID_TIER = frozenset({"L0", "L1", "L2", "L3"})


def resolve_tier(broker_id: str, *, live: bool = False) -> CertTier:
    """Map broker + context to ADR-018 certification tier."""
    if live:
        return "L3"
    if broker_id == "paper":
        return "L1"
    return "L2"


def resolve_status(*, passed: bool, blocked: bool = False) -> SchemaStatus:
    if blocked:
        return "blocked"
    return "passed" if passed else "failed"


def validate_verify_report(data: dict[str, Any]) -> list[str]:
    """Return validation errors for a verify report dict (empty = valid)."""
    errors: list[str] = []
    missing = _VERIFY_REQUIRED - data.keys()
    if missing:
        errors.append(f"missing keys: {sorted(missing)}")
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    tier = data.get("tier")
    if tier not in _VALID_TIER:
        errors.append(f"invalid tier: {tier!r}")
    status = data.get("status")
    if status not in _VALID_STATUS:
        errors.append(f"invalid status: {status!r}")
    steps = data.get("steps")
    if not isinstance(steps, list):
        errors.append("steps must be a list")
    elif steps:
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                errors.append(f"steps[{i}] must be an object")
                continue
            for key in ("name", "passed"):
                if key not in step:
                    errors.append(f"steps[{i}] missing {key}")
    return errors


def validate_certification_report(data: dict[str, Any]) -> list[str]:
    """Return validation errors for a certification report dict (empty = valid)."""
    errors: list[str] = []
    missing = _CERT_REQUIRED - data.keys()
    if missing:
        errors.append(f"missing keys: {sorted(missing)}")
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    tier = data.get("tier")
    if tier not in _VALID_TIER:
        errors.append(f"invalid tier: {tier!r}")
    status = data.get("status")
    if status not in _VALID_STATUS:
        errors.append(f"invalid status: {status!r}")
    results = data.get("results")
    if not isinstance(results, list):
        errors.append("results must be a list")
    elif results:
        for i, row in enumerate(results):
            if not isinstance(row, dict):
                errors.append(f"results[{i}] must be an object")
                continue
            for key in ("area", "passed"):
                if key not in row:
                    errors.append(f"results[{i}] missing {key}")
    return errors
