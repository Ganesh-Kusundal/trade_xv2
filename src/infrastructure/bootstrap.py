"""Runtime composition-root builders for OMS infrastructure.

``application.oms`` depends on ports only. Callers that need concrete
EventBus / order store / DLQ instances import builders from here.

A thin re-export remains at ``brokers.common.oms.defaults`` for older
call sites; prefer this module in new code.
"""

from __future__ import annotations

from typing import Any


def build_event_bus(
    event_log: Any = None,
    metrics: Any = None,
    dead_letter_queue: Any = None,
    resilience: Any | None = None,
) -> Any:
    """Construct the concrete ``EventBus`` with the given collaborators.

    When ``resilience`` (a ``runtime.resilience.ResilienceConfig``) is provided,
    its ``event_log_enabled`` and ``idempotency_ttl_seconds`` (mapped to the
    bus idempotency cache size) are applied. This keeps the resilience
    subsystem a single visible knob instead of scattered env-var reads.
    """
    from infrastructure.event_bus import EventBus

    logging_enabled = True
    max_processed_events = 10_000
    if resilience is not None:
        logging_enabled = resilience.event_log_enabled
        # Map the idempotency TTL (seconds) to a rough cache bound: 1 entry per
        # second of retention, capped to avoid unbounded memory. The bus uses
        # this only for duplicate-event suppression, not the OMS idempotency.
        max_processed_events = max(1_000, min(resilience.idempotency_ttl_seconds, 1_000_000))

    return EventBus(
        event_log=event_log,
        metrics=metrics,
        dead_letter_queue=dead_letter_queue,
        logging_enabled=logging_enabled,
        max_processed_events=max_processed_events,
    )


def build_async_event_bus(
    sync_bus: Any,
    resilience: Any | None = None,
) -> Any:
    """Wrap a sync ``EventBus`` in an ``AsyncEventBus`` sized from resilience config."""
    from infrastructure.event_bus import AsyncEventBus

    max_queue = 10_000
    if resilience is not None:
        max_queue = resilience.max_async_bus_queue
    return AsyncEventBus(sync_bus, max_queue_size=max_queue)


def build_resilient_event_bus(
    resilience: Any | None = None,
    *,
    event_log: Any = None,
) -> Any:
    """Production ``EventBus`` whose resilience knobs come from ``resilience``."""
    from infrastructure.observability.event_metrics import EventMetrics

    return build_event_bus(
        event_log=event_log,
        metrics=EventMetrics(),
        dead_letter_queue=build_dead_letter_queue(),
        resilience=resilience,
    )


def build_processed_trade_repository() -> Any:
    """Construct the concrete in-memory idempotency ledger."""
    from infrastructure.event_bus import ProcessedTradeRepository

    return ProcessedTradeRepository()


def build_dead_letter_queue() -> Any:
    """Construct the default persistent dead-letter queue."""
    from infrastructure.event_bus.persistent_dead_letter_queue import (
        create_default_dead_letter_queue,
    )

    return create_default_dead_letter_queue()


def build_order_store(db_path: str | None = None) -> Any:
    """Construct the concrete durable order store (``SqliteOrderStore``)."""
    from infrastructure.persistence.sqlite_order_store import SqliteOrderStore

    return SqliteOrderStore(db_path=db_path) if db_path else SqliteOrderStore()


def build_execution_ledger(db_path: str | None = None) -> Any:
    """Construct the durable pre-submit execution ledger."""
    from infrastructure.persistence.sqlite_execution_ledger import SqliteExecutionLedger

    return SqliteExecutionLedger(db_path or "market_data/execution_ledger.sqlite")


def build_production_event_bus(*, event_log: Any = None, resilience: Any | None = None) -> Any:
    """EventBus with production collaborators (metrics + DLQ).

    Pass ``resilience`` (``runtime.resilience.ResilienceConfig``) to apply the
    resilience subsystem's event-log / idempotency knobs.
    """
    from infrastructure.observability.event_metrics import EventMetrics

    return build_event_bus(
        event_log=event_log,
        metrics=EventMetrics(),
        dead_letter_queue=build_dead_letter_queue(),
        resilience=resilience,
    )
