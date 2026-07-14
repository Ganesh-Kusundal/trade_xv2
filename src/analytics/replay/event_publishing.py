"""Event publishing helpers for ReplayEngine.

P0-1: Scheduled events are published in time order relative to bar
processing, ensuring deterministic replay that matches the original
event/bar interleaving.
"""

from __future__ import annotations

import logging

import pandas as pd

from analytics.strategy.models import Signal

logger = logging.getLogger(__name__)


def publish_scheduled_events(
    event_bus,
    event_schedule: dict[pd.Timestamp, list],
    bar_ts: pd.Timestamp,
) -> None:
    """Publish any scheduled events with timestamp <= current bar timestamp.

    Parameters
    ----------
    event_bus:
        EventBus instance to publish to.
    event_schedule:
        Map of timestamps to lists of DomainEvents.
    bar_ts:
        Timestamp of the current bar being processed.
    """
    scheduled_ts = sorted(event_schedule.keys())
    for evt_ts in scheduled_ts:
        if evt_ts > bar_ts:
            break
        events = event_schedule.get(evt_ts)
        if events is None:
            continue
        for event in events:
            try:
                event_bus.publish(event)
            except Exception as exc:
                logger.debug("Failed to publish scheduled event at %s: %s", evt_ts, exc)


def publish_signal(event_bus, signal: Signal) -> None:
    """Publish a signal to the EventBus.

    Builds a canonical DomainEvent with the ``SIGNAL_GENERATED`` event type
    so consumers on the bus (metrics, audit, strategies) can react.  Errors
    are swallowed because signal publishing is best-effort; a failed publish
    must never abort the replay bar loop.
    """
    try:
        from domain.events import EventType
        from domain.events.types import DomainEvent

        event = DomainEvent.now(
            event_type=EventType.SIGNAL_GENERATED.value,
            payload={
                "symbol": signal.symbol,
                "strategy": signal.strategy,
                "signal_type": signal.signal_type.value
                if hasattr(signal.signal_type, "value")
                else str(signal.signal_type),
                "score": getattr(signal, "score", None),
                "confidence": getattr(signal, "confidence", None),
            },
            symbol=signal.symbol,
            source=f"replay:{signal.strategy}",
        )
        event_bus.publish(event)
    except Exception as exc:
        logger.debug("Failed to publish signal event: %s", exc)
