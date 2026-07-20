"""Canonical developer platform operations (TRANS-P4-002).

Single import surface for ``verify``, ``certify``, ``doctor``, ``diagnose``,
``health``, and ``benchmark``. Used by broker CLI, MCP, tradex certify, and
Used by broker CLI, MCP, tradex certify, and UI doctor command.
"""

from __future__ import annotations

from brokers.services.core import (
    run_benchmark,
    run_certify,
    run_diagnose,
    run_doctor,
    run_health,
    run_mapping,
    run_verify,
    VerifyReport,
)

__all__ = [
    "VerifyReport",
    "run_benchmark",
    "run_certify",
    "run_diagnose",
    "run_doctor",
    "run_health",
    "run_mapping",
    "run_verify",
]