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
) -> Any:
    """Construct the concrete ``EventBus`` with the given collaborators."""
    from infrastructure.event_bus import EventBus

    return EventBus(
        event_log=event_log,
        metrics=metrics,
        dead_letter_queue=dead_letter_queue,
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
