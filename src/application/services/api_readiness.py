"""API readiness evaluation — shared /readyz semantics (TRANS-P4-005).

Aligns with TradingContext placement gates and DEVELOPER-PLATFORM.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

GateStatus = Literal["passed", "failed", "blocked"]


@dataclass(frozen=True)
class ReadinessGate:
    id: str
    status: GateStatus
    message: str = ""


@dataclass
class ApiReadinessReport:
    ready: bool
    checks: list[ReadinessGate] = field(default_factory=list)

    def as_bool_map(self) -> dict[str, bool]:
        return {c.id: c.status == "passed" for c in self.checks}

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "checks": [
                {"id": c.id, "status": c.status, "message": c.message} for c in self.checks
            ],
            "checks_bool": self.as_bool_map(),
        }


def _gate(id_: str, ok: bool, *, message: str = "", blocked: bool = False) -> ReadinessGate:
    if ok:
        return ReadinessGate(id_, "passed", message or "ok")
    if blocked:
        return ReadinessGate(id_, "blocked", message or "not available")
    return ReadinessGate(id_, "failed", message or "check failed")


def evaluate_api_readiness(container: Any) -> ApiReadinessReport:
    """Evaluate API readiness from the service container."""
    gates: list[ReadinessGate] = []

    gates.append(_gate("container", container is not None))
    if container is None:
        return ApiReadinessReport(ready=False, checks=gates)

    for svc_id, attr in (
        ("datalake_gateway", "datalake_gateway"),
        ("view_manager", "view_manager"),
        ("data_catalog", "data_catalog"),
    ):
        gates.append(_gate(svc_id, getattr(container, attr, None) is not None))

    event_bus = getattr(container, "event_bus", None)
    trading_context = getattr(container, "trading_context", None)
    if event_bus is None and trading_context is not None:
        event_bus = getattr(trading_context, "event_bus", None)
    gates.append(_gate("event_bus", event_bus is not None))

    gates.append(_gate("oms_context", trading_context is not None))
    if trading_context is not None:
        health = trading_context.health() if hasattr(trading_context, "health") else {}
        recon_ok = bool(health.get("reconciliation_ready", False))
        gates.append(
            _gate(
                "reconciliation_ready",
                recon_ok,
                message="placement gate open" if recon_ok else "awaiting first reconciliation",
                blocked=not recon_ok,
            )
        )

    broker_service = getattr(container, "broker_service", None)
    if broker_service is not None:
        gw = getattr(broker_service, "active_broker", None)
        live = bool(getattr(broker_service, "live_actionable", False))
        live_intent = broker_service.live_intent if hasattr(broker_service, 'live_intent') else False
        gates.append(
            _gate(
                "broker_session",
                gw is not None or not live_intent,
                message="gateway wired" if gw is not None else "no live gateway",
                blocked=gw is None and live_intent,
            )
        )
        if live_intent:
            from application.services.production_readiness import ProductionReadinessChecker

            prod = ProductionReadinessChecker(broker_service).run()
            gates.append(
                _gate(
                    "production_readiness",
                    prod.passed,
                    message=prod.summary(),
                )
            )
        elif live:
            gates.append(_gate("live_actionable", live, message="broker session actionable"))

    ready = all(c.status == "passed" for c in gates)
    return ApiReadinessReport(ready=ready, checks=gates)