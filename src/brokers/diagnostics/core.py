"""BrokerDiagnostics — shared diagnostic engine for the Trading OS broker layer.

This is the single implementation core behind the three equivalent front-ends
(Python SDK, CLI, MCP). It runs checks against a :class:`BrokerSession` and
returns structured results so every interface shows identical output.

Reuses the existing ``infrastructure.health`` checks where possible; never
re-implements broker connectivity logic.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from brokers.session import BrokerSession


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    SKIP = "SKIP"


@dataclass
class CheckResult:
    """Structured result of a single diagnostic check."""

    name: str
    status: CheckStatus
    detail: str = ""
    latency_ms: float | None = None

    def as_tuple(self) -> tuple[str, str, str]:
        return (self.name, self.status.value, self.detail)


@dataclass
class DiagnosticReport:
    """Collection of check results for one diagnostic run."""

    broker_id: str
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, result: CheckResult) -> CheckResult:
        self.checks.append(result)
        return result

    def run(self, name: str, fn: Callable[[], str], *, warn_only: bool = False) -> CheckResult:
        """Run ``fn`` (returns a detail string) and record PASS/FAIL."""
        start = time.perf_counter()
        try:
            detail = fn()
            status = CheckStatus.PASS
        except NotImplementedError:
            status = CheckStatus.WARNING if warn_only else CheckStatus.FAIL
            detail = "Not implemented for this broker"
        except Exception as exc:  # noqa: BLE001
            status = CheckStatus.WARNING if warn_only else CheckStatus.FAIL
            detail = f"{type(exc).__name__}: {exc}"
        latency = (time.perf_counter() - start) * 1000.0
        return self.add(CheckResult(name, status, detail or "OK", round(latency, 2)))

    @property
    def all_passed(self) -> bool:
        return all(c.status == CheckStatus.PASS for c in self.checks)

    @property
    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status == CheckStatus.FAIL]

    def print_report(self) -> None:
        print(f"Diagnostics for broker '{self.broker_id}':")
        for c in self.checks:
            print(f"  [{c.status.value}] {c.name}: {c.detail}  ({c.latency_ms}ms)")
        verdict = "PASS" if self.all_passed else f"{len(self.failed)} FAILED"
        print(f"Overall: {verdict}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "broker_id": self.broker_id,
            "all_passed": self.all_passed,
            "checks": [vars(c) for c in self.checks],
        }


class BrokerDiagnostics:
    """Runs connectivity, authentication, and API sanity checks on any broker."""

    def __init__(self, session: BrokerSession) -> None:
        self._session = session
        self._broker_id = session.broker_id

    def run_all_checks(self) -> DiagnosticReport:
        """Run the standard diagnostic check set against the session."""
        report = DiagnosticReport(self._broker_id)
        s = self._session

        report.run("Authentication", lambda: _detail_funds(s))
        report.run("Quote", lambda: _detail_quote(s))
        report.run("Historical Data", lambda: _detail_history(s))
        report.run("Capabilities", lambda: _detail_capabilities(s))
        report.run("Instrument Resolution", lambda: _detail_resolve(s))
        report.run("Option Chain", lambda: _detail_option_chain(s), warn_only=True)
        report.run("Subscription", lambda: _detail_subscribe(s), warn_only=True)
        return report


# ── Detail helpers (operate on a BrokerSession, not a raw gateway) ──────────


def _detail_funds(s: BrokerSession) -> str:
    acct = s.account
    funds = getattr(acct, "funds", None)
    if callable(funds):
        try:
            funds = funds()
        except Exception:
            funds = None
    if funds is None:
        return "Connected (funds not exposed by this broker)"
    return f"Connected. Available: {_safe_balance(funds)}"


def _safe_balance(funds: Any) -> str:
    if isinstance(funds, dict):
        val = funds.get("available_balance", funds.get("available_margin", "n/a"))
    else:
        val = getattr(funds, "available_balance", getattr(funds, "available_margin", "n/a"))
    return f"{float(val):,.2f}" if isinstance(val, (int, float)) else str(val)


def _detail_quote(s: BrokerSession) -> str:
    stock = s.stock("RELIANCE")
    q = stock.refresh()
    if q is None or getattr(q, "ltp", None) is None:
        raise RuntimeError("no quote returned")
    return f"LTP={q.ltp}"


def _detail_history(s: BrokerSession) -> str:
    stock = s.stock("RELIANCE")
    series = s.history(stock, timeframe="1D", days=7)
    n = getattr(series, "bar_count", 0)
    if not n:
        raise RuntimeError("no historical data returned")
    return f"{n} candles retrieved"


def _detail_capabilities(s: BrokerSession) -> str:
    stock = s.stock("RELIANCE")
    caps = stock.capabilities()
    return f"{len(caps)} capabilities: {', '.join(caps) or 'none'}"


def _detail_resolve(s: BrokerSession) -> str:
    inst = s.stock("RELIANCE")
    if inst is None or inst.symbol != "RELIANCE":
        raise RuntimeError("instrument resolution failed")
    return f"Resolved RELIANCE -> {inst.id}"


def _detail_option_chain(s: BrokerSession) -> str:
    chain = s.option_chain("NIFTY")
    n = len(getattr(chain, "strikes", []) or [])
    return f"{n} strikes available" if n else "empty chain (acceptable for paper)"


def _detail_subscribe(s: BrokerSession) -> str:
    stock = s.stock("RELIANCE")
    handle = s.subscribe(stock)
    if handle is None:
        raise RuntimeError("subscription returned no handle")
    try:
        s.unsubscribe(stock)
    except Exception:
        pass
    return "subscription active"