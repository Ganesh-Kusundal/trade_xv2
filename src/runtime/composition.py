"""Neutral composition helpers for runtime/API bootstrap."""

from __future__ import annotations

from typing import Any


def wire_domain_port_sinks() -> None:
    """Register infrastructure adapters on domain ports (idempotent)."""
    from domain.ports.audit import AuditSink, set_audit_sink
    from domain.ports.io import set_parquet_writer
    from domain.ports.security import set_secure_session_asserter
    from infrastructure.io.parquet import atomic_parquet_write
    from infrastructure.observability import audit as infra_audit
    from infrastructure.security.ssl_hardening import assert_secure_session

    set_audit_sink(
        AuditSink(
            emit_routing_decision=infra_audit.emit_routing_decision,
            emit_quota_event=infra_audit.emit_quota_event,
            emit_historical_chunk=infra_audit.emit_historical_chunk,
            emit_merge_conflict=infra_audit.emit_merge_conflict,
            emit_stream_state_change=infra_audit.emit_stream_state_change,
        )
    )
    set_parquet_writer(atomic_parquet_write)
    set_secure_session_asserter(assert_secure_session)


def create_api_event_bus(*, maxsize: int = 2000) -> tuple[Any, Any]:
    """Create the shared EventBus used by API bootstrap (metrics + DLQ)."""
    from infrastructure.bootstrap import build_production_event_bus
    from runtime.resilience import ResilienceConfig

    wire_domain_port_sinks()
    bus = build_production_event_bus(resilience=ResilienceConfig.from_env())
    config = {
        "maxsize": maxsize,
        "created_by": "create_api_event_bus",
        "bus_type": "synchronous",
    }
    return bus, config
