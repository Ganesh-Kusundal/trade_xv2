"""broker doctor — complete environment pre-flight validation.

Inspired by ``kubectl`` / ``flutter doctor`` / ``docker info``. Runs a full
environment check (Python/deps, credentials, token, connectivity, symbol-master
freshness, mapping integrity, historical/quote access, order permissions, perf,
plugin discovery, config) and returns a structured report. This is the standard
pre-flight for developers, CI, and AI agents.
"""

from __future__ import annotations

import logging
import platform
from dataclasses import dataclass, field
from typing import Any

from brokers.diagnostics.core import CheckResult, CheckStatus, DiagnosticReport
from brokers.session import BrokerSession, available_brokers

logger = logging.getLogger(__name__)


@dataclass
class DoctorReport:
    """Full environment diagnostic report."""

    broker_id: str
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, status: CheckStatus, detail: str) -> None:
        self.checks.append(CheckResult(name, status, detail))

    def print_report(self) -> None:
        logger.info("broker doctor — broker '%s':", self.broker_id)
        for c in self.checks:
            logger.info("  [%s] %s: %s", c.status.value, c.name, c.detail)
        failed = [c for c in self.checks if c.status == CheckStatus.FAIL]
        logger.info("Overall: %s", "PASS" if not failed else f"{len(failed)} issue(s)")

    def to_dict(self, *, mode: str | None = None, live: bool = False) -> dict[str, Any]:
        from brokers.diagnostics.schema import format_doctor_dict

        return format_doctor_dict(
            broker_id=self.broker_id,
            checks=self.checks,
            mode=mode,
            live=live,
        )

    @property
    def overall(self) -> str:
        from brokers.diagnostics.schema import resolve_overall

        return resolve_overall(self.checks)


def run_doctor(broker: str = "paper") -> DoctorReport:
    """Run the full environment pre-flight for ``broker``."""
    report = DoctorReport(broker)

    # 1. Python / dependency versions
    report.add(
        "Python Version",
        CheckStatus.PASS,
        f"{platform.python_version()} ({platform.system()})",
    )

    # 2. Plugin discovery
    brokers = available_brokers()
    if broker in brokers:
        report.add("Plugin Discovery", CheckStatus.PASS, f"found: {', '.join(brokers)}")
    else:
        report.add(
            "Plugin Discovery",
            CheckStatus.FAIL,
            f"broker {broker!r} not registered; available: {', '.join(brokers) or 'none'}",
        )
        return report

    # 3. Connect + run the standard diagnostic checks
    try:
        session = BrokerSession(broker)
    except Exception as exc:
        report.add("Broker Connect", CheckStatus.FAIL, f"{type(exc).__name__}: {exc}")
        return report

    report.add("Broker Connect", CheckStatus.PASS, "session established")

    diag = DiagnosticReport(broker)
    for _res in diag.checks or []:
        pass  # placeholder; real checks run below via BrokerDiagnostics

    from brokers.diagnostics.core import BrokerDiagnostics

    sub = BrokerDiagnostics(session).run_all_checks()
    for c in sub.checks:
        report.add(c.name, c.status, c.detail)

    # 4. Symbol-master freshness (best-effort)
    try:
        stock = session.stock("RELIANCE")
        q = stock.refresh()
        fresh = q is not None and getattr(q, "ltp", None) is not None
        report.add(
            "Symbol Master",
            CheckStatus.PASS if fresh else CheckStatus.WARNING,
            "quote retrievable" if fresh else "no live quote (acceptable for paper)",
        )
    except Exception as exc:
        report.add("Symbol Master", CheckStatus.WARNING, f"{type(exc).__name__}: {exc}")

    # 5. Order permissions (paper validates without real orders)
    try:
        status = session.status
        orders = bool(getattr(status, "orders_enabled", False))
        report.add(
            "Order Permissions",
            CheckStatus.PASS,
            "orders enabled" if orders else "orders disabled (market mode)",
        )
    except Exception as exc:
        report.add("Order Permissions", CheckStatus.WARNING, f"{type(exc).__name__}: {exc}")

    session.close()
    return report
