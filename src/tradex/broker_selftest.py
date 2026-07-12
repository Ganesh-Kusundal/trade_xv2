"""Broker self-test: fail-fast startup validation (TRADEX_BROKER_SELFTEST=1).

Extracted from ``tradex.session``. Runs a quick capability probe against the
freshly built session and raises :class:`ConnectError` on any failure.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from domain.connect_errors import ConnectError, GATEWAY_FAILED
from domain.universe import Session as DomainSession

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    raw = (os.environ.get("TRADEX_BROKER_SELFTEST") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def run(session: DomainSession, broker_id: str) -> None:
    """Fail-fast startup validation when TRADEX_BROKER_SELFTEST=1."""
    from brokers.services.core import VerifyReport

    report = VerifyReport(broker_id=broker_id)
    report.add("Configuration", True, f"broker={broker_id}")
    st = getattr(session, "status", None)
    report.add("Authentication", bool(getattr(st, "authenticated", False)), getattr(st, "mode", "?"))
    try:
        stock = session.universe.equity("RELIANCE")
        caps = stock.capabilities()
        report.add("Capabilities", True, f"{len(caps)} reported")
        if stock.id.underlying.upper() != "RELIANCE":
            report.add("Mappings", False, "symbol mismatch")
        else:
            report.add("Mappings", True)
        q = stock.refresh()
        report.add("Sample Quote", q is not None)
        hist = stock.history(timeframe="1D", days=1)
        report.add("Historical", bool(getattr(hist, "bar_count", 0)))
        handle = stock.subscribe()
        report.add("WebSocket", handle is not None)
        if handle is not None:
            stock.unsubscribe()
    except Exception as exc:  # noqa: BLE001
        report.add("SelfTest", False, f"{type(exc).__name__}: {exc}")
        raise ConnectError(
            f"Broker self-test failed for {broker_id!r}.",
            code=GATEWAY_FAILED,
            broker_id=broker_id,
            remediation="Run: broker verify " + broker_id,
            details={"error": str(exc)},
        ) from exc
    if not all(s.passed for s in report.steps):
        failed = [s.name for s in report.steps if not s.passed]
        raise ConnectError(
            f"Broker self-test failed: {', '.join(failed)}",
            code=GATEWAY_FAILED,
            broker_id=broker_id,
            remediation="Run: broker verify " + broker_id,
        )
