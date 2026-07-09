"""Default builders for OMS event infrastructure.

``application.oms`` depends on the event-bus / event-log / idempotency-ledger
*ports* and receives concrete instances via injection.  When a caller does not
supply them (e.g. ``TradingContext()`` constructed with no arguments), these
builders construct the infrastructure defaults.

This module lives in ``brokers.common`` (which is permitted to depend on
``infrastructure``) so that ``application`` stays free of any
``infrastructure`` import.  It is an incremental step toward a single
composition root (see debt item D11); the long-term plan moves default wiring
into the runtime composition root.
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
