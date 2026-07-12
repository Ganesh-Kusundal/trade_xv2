"""Brokers diagnostics — shared engine behind SDK / CLI / MCP front-ends."""

from __future__ import annotations

from brokers.diagnostics.benchmark import BenchmarkReport, run_benchmark
from brokers.diagnostics.core import (
    BrokerDiagnostics,
    CheckResult,
    CheckStatus,
    DiagnosticReport,
)
from brokers.diagnostics.doctor import DoctorReport, run_doctor
from brokers.diagnostics.health import HealthReport, run_health

__all__ = [
    "BrokerDiagnostics",
    "CheckResult",
    "CheckStatus",
    "DiagnosticReport",
    "DoctorReport",
    "HealthReport",
    "BenchmarkReport",
    "run_doctor",
    "run_health",
    "run_benchmark",
]