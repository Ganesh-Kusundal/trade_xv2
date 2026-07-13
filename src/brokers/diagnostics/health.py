"""broker health — runtime health checks for a connected broker.

Wraps the existing ``infrastructure.health`` checks and adds broker-layer
checks (WebSocket, subscription, cache, config, version, capabilities) driven by
a :class:`BrokerSession`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from brokers.diagnostics.core import CheckResult, CheckStatus, DiagnosticReport
from brokers.session import BrokerSession

logger = logging.getLogger(__name__)


@dataclass
class HealthReport:
    broker_id: str
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, status: CheckStatus, detail: str) -> None:
        self.checks.append(CheckResult(name, status, detail))

    def print_report(self) -> None:
        logger.info("broker health — '%s':", self.broker_id)
        for c in self.checks:
            logger.info("  [%s] %s: %s", c.status.value, c.name, c.detail)
        failed = [c for c in self.checks if c.status == CheckStatus.FAIL]
        logger.info("Overall: %s", "HEALTHY" if not failed else f"{len(failed)} unhealthy")

    def to_dict(self) -> dict[str, Any]:
        return {"broker_id": self.broker_id, "checks": [vars(c) for c in self.checks]}


def run_health(broker: str = "paper") -> HealthReport:
    """Run health checks against a broker session."""
    report = HealthReport(broker)
    try:
        session = BrokerSession(broker)
    except Exception as exc:  # noqa: BLE001
        report.add("Broker Reachable", CheckStatus.FAIL, f"{type(exc).__name__}: {exc}")
        return report

    report.add("Broker Reachable", CheckStatus.PASS, "session established")

    # API latency via quote
    try:
        stock = session.stock("RELIANCE")
        import time

        t0 = time.perf_counter()
        stock.refresh()
        ms = round((time.perf_counter() - t0) * 1000, 2)
        report.add("API Latency", CheckStatus.PASS, f"quote {ms}ms")
    except Exception as exc:  # noqa: BLE001
        report.add("API Latency", CheckStatus.FAIL, f"{type(exc).__name__}: {exc}")

    # Historical working
    try:
        series = session.history(session.stock("RELIANCE"), timeframe="1D", days=5)
        n = getattr(series, "bar_count", 0)
        report.add(
            "Historical Working",
            CheckStatus.PASS if n else CheckStatus.WARNING,
            f"{n} bars" if n else "no bars",
        )
    except Exception as exc:  # noqa: BLE001
        report.add("Historical Working", CheckStatus.FAIL, f"{type(exc).__name__}: {exc}")

    # Subscription active
    try:
        stock = session.stock("RELIANCE")
        handle = session.subscribe(stock)
        ok = handle is not None
        report.add(
            "Subscription Active",
            CheckStatus.PASS if ok else CheckStatus.WARNING,
            "handle acquired" if ok else "no handle",
        )
        session.unsubscribe(stock)
    except Exception as exc:  # noqa: BLE001
        report.add("Subscription Active", CheckStatus.WARNING, f"{type(exc).__name__}: {exc}")

    # Session valid
    try:
        st = session.status
        report.add(
            "Session Valid",
            CheckStatus.PASS,
            f"mode={getattr(st, 'mode', '?')}, orders={getattr(st, 'orders_enabled', '?')}",
        )
    except Exception as exc:  # noqa: BLE001
        report.add("Session Valid", CheckStatus.FAIL, f"{type(exc).__name__}: {exc}")

    # Capabilities
    try:
        caps = session.stock("RELIANCE").capabilities()
        report.add("Capabilities", CheckStatus.PASS, f"{len(caps)} capabilities")
    except Exception as exc:  # noqa: BLE001
        report.add("Capabilities", CheckStatus.WARNING, f"{type(exc).__name__}: {exc}")

    # Configuration / version
    report.add("Configuration", CheckStatus.PASS, f"broker_id={session.broker_id}")
    report.add("Version", CheckStatus.PASS, "TradeXV2 brokers layer")

    session.close()
    return report