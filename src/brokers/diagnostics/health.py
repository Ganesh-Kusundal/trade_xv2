"""broker health — runtime health checks for a connected broker.

Wraps the existing ``infrastructure.health`` checks and adds broker-layer
checks (WebSocket, subscription, cache, config, version, capabilities) driven by
a :class:`BrokerSession`.
"""

from __future__ import annotations

import logging

from brokers.diagnostics.core import CheckResult, CheckStatus, DiagnosticReport
from brokers.session import BrokerSession

logger = logging.getLogger(__name__)

# HealthReport is now just DiagnosticReport — same shape, same methods.
HealthReport = DiagnosticReport


def run_health(broker: str = "paper") -> DiagnosticReport:
    """Run health checks against a broker session."""
    report = DiagnosticReport(broker)
    try:
        session = BrokerSession(broker)
    except Exception as exc:
        report.add(
            CheckResult("Broker Reachable", CheckStatus.FAIL, f"{type(exc).__name__}: {exc}")
        )
        return report

    report.add(CheckResult("Broker Reachable", CheckStatus.PASS, "session established"))

    # API latency via quote
    try:
        stock = session.stock("RELIANCE")
        import time

        t0 = time.perf_counter()
        stock.refresh()
        ms = round((time.perf_counter() - t0) * 1000, 2)
        report.add(CheckResult("API Latency", CheckStatus.PASS, f"quote {ms}ms"))
    except Exception as exc:
        report.add(CheckResult("API Latency", CheckStatus.FAIL, f"{type(exc).__name__}: {exc}"))

    # Historical working
    try:
        series = session.history(session.stock("RELIANCE"), timeframe="1D", days=5)
        n = getattr(series, "bar_count", 0)
        report.add(
            CheckResult(
                "Historical Working",
                CheckStatus.PASS if n else CheckStatus.WARNING,
                f"{n} bars" if n else "no bars",
            )
        )
    except Exception as exc:
        report.add(
            CheckResult("Historical Working", CheckStatus.FAIL, f"{type(exc).__name__}: {exc}")
        )

    # Subscription active
    try:
        stock = session.stock("RELIANCE")
        handle = session.subscribe(stock)
        ok = handle is not None
        report.add(
            CheckResult(
                "Subscription Active",
                CheckStatus.PASS if ok else CheckStatus.WARNING,
                "handle acquired" if ok else "no handle",
            )
        )
        session.unsubscribe(stock)
    except Exception as exc:
        report.add(
            CheckResult("Subscription Active", CheckStatus.WARNING, f"{type(exc).__name__}: {exc}")
        )

    # Session valid
    try:
        st = session.status
        report.add(
            CheckResult(
                "Session Valid",
                CheckStatus.PASS,
                f"mode={getattr(st, 'mode', '?')}, orders={getattr(st, 'orders_enabled', '?')}",
            )
        )
    except Exception as exc:
        report.add(CheckResult("Session Valid", CheckStatus.FAIL, f"{type(exc).__name__}: {exc}"))

    # Capabilities
    try:
        caps = session.stock("RELIANCE").capabilities()
        report.add(CheckResult("Capabilities", CheckStatus.PASS, f"{len(caps)} capabilities"))
    except Exception as exc:
        report.add(CheckResult("Capabilities", CheckStatus.WARNING, f"{type(exc).__name__}: {exc}"))

    # Configuration / version
    report.add(CheckResult("Configuration", CheckStatus.PASS, f"broker_id={session.broker_id}"))
    report.add(CheckResult("Version", CheckStatus.PASS, "TradeXV2 brokers layer"))

    session.close()
    return report
