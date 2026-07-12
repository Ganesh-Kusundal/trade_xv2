"""Operations services — certification, diagnostics, health, and self-test flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from brokers.session import BrokerSession, available_brokers

from ._session import _open
from .capabilities import format_session_capabilities


def run_mapping(
    broker: str = "paper",
    *,
    session: BrokerSession | None = None,
) -> Any:
    from brokers.certification.mapping import verify_mapping

    return verify_mapping(broker, session=session)


def run_market_hours(broker: str = "paper", **kwargs: Any) -> Any:
    from brokers.certification.market_hours import verify_market_hours

    return verify_market_hours(broker, **kwargs)


def run_certify(broker: str = "paper", *, live: bool = False, **kwargs: Any) -> Any:
    from brokers.certification.suite import BrokerCertifier

    s = _open(broker, **kwargs)
    try:
        return BrokerCertifier(s).certify()
    finally:
        s.close()


def run_diagnose(broker: str = "paper", **kwargs: Any) -> Any:
    from brokers.diagnostics.core import BrokerDiagnostics

    s = _open(broker, **kwargs)
    try:
        return BrokerDiagnostics(s).run_all_checks()
    finally:
        s.close()


def run_doctor(broker: str = "paper") -> Any:
    from brokers.diagnostics.doctor import run_doctor as _run_doctor

    return _run_doctor(broker)


def run_health(broker: str = "paper") -> Any:
    from brokers.diagnostics.health import run_health as _run_health

    return _run_health(broker)


def run_benchmark(broker: str = "paper") -> Any:
    from brokers.diagnostics.benchmark import run_benchmark as _run_benchmark

    return _run_benchmark(broker)


@dataclass
class VerifyStep:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class VerifyReport:
    broker_id: str
    steps: list[VerifyStep] = field(default_factory=list)
    certified: bool = False

    @property
    def passed(self) -> bool:
        return all(s.passed for s in self.steps) and self.certified

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.steps.append(VerifyStep(name, passed, detail))

    def print_report(self) -> None:
        for step in self.steps:
            mark = "PASS" if step.passed else "FAIL"
            suffix = f" ({step.detail})" if step.detail else ""
            print(f"[{mark}] {step.name}{suffix}")
        print(f"Overall: {'PASS' if self.passed else 'FAIL'}")

    def to_dict(self) -> dict[str, Any]:
        from brokers.certification.schema_v2 import (
            SCHEMA_VERSION,
            resolve_status,
            resolve_tier,
        )

        return {
            "schema_version": SCHEMA_VERSION,
            "broker_id": self.broker_id,
            "tier": resolve_tier(self.broker_id),
            "status": resolve_status(passed=self.passed),
            "passed": self.passed,
            "certified": self.certified,
            "steps": [{"name": s.name, "passed": s.passed, "detail": s.detail} for s in self.steps],
        }


def run_verify(broker: str = "paper", **kwargs: Any) -> VerifyReport:
    """Startup self-test: config → auth → caps → mappings → quote → history → ws → certify."""
    from brokers.certification.mapping import verify_mapping
    from brokers.certification.market_hours import is_nse_market_open
    from brokers.certification.suite import BrokerCertifier

    report = VerifyReport(broker_id=broker)
    if broker not in available_brokers():
        report.add("Configuration", False, f"unknown broker; available: {', '.join(available_brokers())}")
        return report

    report.add("Configuration", True, f"broker={broker}")
    report.add("Secrets", True, "env resolved")

    try:
        s = _open(broker, **kwargs)
    except Exception as exc:  # noqa: BLE001
        report.add("Broker Connect", False, f"{type(exc).__name__}: {exc}")
        return report

    try:
        report.add("Broker Plugin", True, f"{broker} registered")
        report.add("Authentication", True, f"mode={getattr(s.status, 'mode', '?')}")

        caps = format_session_capabilities(s)
        matrix = caps.get("matrix") or {}
        report.add("Capabilities", bool(matrix), f"{len(caps.get('extensions', []))} extensions")

        mapping = verify_mapping(broker, session=s)
        report.add("Mappings", mapping.all_passed)

        q = s.stock("RELIANCE").refresh()
        report.add("Sample Quote", q is not None)

        hist = s.history(s.stock("RELIANCE"), timeframe="1D", days=30)
        report.add("Historical", bool(getattr(hist, "bar_count", 0)))

        if is_nse_market_open():
            handle = s.subscribe(s.stock("RELIANCE"))
            report.add("WebSocket", handle is not None)
            if handle is not None:
                s.unsubscribe(s.stock("RELIANCE"))
        else:
            report.add("WebSocket", True, "off-market (skipped)")

        cert = BrokerCertifier(s).certify()
        report.certified = cert.is_certified
    finally:
        s.close()

    return report


__all__ = [
    "run_mapping",
    "run_market_hours",
    "run_certify",
    "run_diagnose",
    "run_doctor",
    "run_health",
    "run_benchmark",
    "VerifyStep",
    "VerifyReport",
    "run_verify",
]
