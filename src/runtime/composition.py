"""Single composition root helpers and domain port sink wiring (ADR-017)."""

from __future__ import annotations

from typing import Any


def wire_domain_port_sinks() -> None:
    """Register infrastructure adapters on domain ports (idempotent)."""
    from application.ports import set_execution_target_resolver
    from domain.ports.async_bridge import set_async_runner, set_dedicated_loop_factory
    from domain.ports.audit import AuditSink, set_audit_sink
    from domain.ports.io import set_parquet_writer
    from domain.ports.security import set_secure_session_asserter
    from infrastructure.io.parquet import atomic_parquet_write
    from infrastructure.observability import audit as infra_audit
    from infrastructure.security.ssl_hardening import assert_secure_session
    from runtime.event_loop import new_dedicated_loop, run_coro_sync
    from runtime.execution_target import (
        resolve_execution_target,
        resolve_simulated_oms_adapter,
    )
    from runtime.session_historical import wire_session_historical

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
    set_async_runner(run_coro_sync)
    set_dedicated_loop_factory(new_dedicated_loop)
    set_execution_target_resolver(resolve_execution_target, resolve_simulated_oms_adapter)
    wire_session_historical()
    from datalake.exchange_registry import wire_exchange_plugins

    wire_exchange_plugins()


def create_api_event_bus(*, maxsize: int = 2000) -> tuple[Any, Any]:
    """Create the shared AsyncEventBus used by API bootstrap (metrics + DLQ)."""
    from infrastructure.bootstrap import build_production_event_bus
    from infrastructure.event_bus.async_event_bus import AsyncEventBus
    from runtime.resilience import ResilienceConfig

    wire_domain_port_sinks()
    sync_bus = build_production_event_bus(resilience=ResilienceConfig.from_env())
    async_bus = AsyncEventBus(sync_bus, max_queue_size=maxsize)
    config = {
        "maxsize": maxsize,
        "created_by": "create_api_event_bus",
        "bus_type": "async",
        "sync_bus": sync_bus,
    }
    return async_bus, config


__all__ = [
    "create_api_event_bus",
    "wire_domain_port_sinks",
]
