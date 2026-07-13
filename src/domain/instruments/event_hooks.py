"""Standalone event-hook system for instrument-domain events.

This is a pure domain utility: it holds no broker logic, no transport
awareness, and no global state. Each :class:`EventHooks` instance keeps
its own callback registries. It can optionally publish emitted events to
an :class:`~domain.ports.event_publisher.EventBusPort` (dependency-injected), but
never imports infrastructure directly.
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import Callable
from enum import Enum
from typing import TYPE_CHECKING, Any

from domain.events.types import DomainEvent

if TYPE_CHECKING:
    from domain.ports.event_publisher import EventBusPort

__all__ = ["InstrumentEvent", "EventHooks"]


class InstrumentEvent(str, Enum):
    """Instrument-domain events that listeners can subscribe to."""

    TICK = "tick"
    QUOTE = "quote"
    DEPTH = "depth"
    TRADE = "trade"
    ORDER = "order"
    DISCONNECT = "disconnect"
    RECONNECT = "reconnect"
    ERROR = "error"


_log = logging.getLogger(__name__)


class EventHooks:
    """Per-instance registry of callbacks for instrument events.

    Pure domain utility. No broker logic, no transport awareness, no
    global mutable state — each instance owns its callback dicts.
    """

    def __init__(self, bus: EventBusPort | None = None) -> None:
        self._bus: EventBusPort | None = bus
        self._callbacks: dict[InstrumentEvent, list[Callable[[Any], None]]] = {
            event: [] for event in InstrumentEvent
        }
        self._any: list[Callable[[InstrumentEvent, Any], None]] = []

    # ── Registration ──────────────────────────────────────────────────

    def register(self, event: InstrumentEvent, callback: Callable[[Any], None]) -> None:
        """Register ``callback`` to be invoked for ``event`` with the payload."""
        if not isinstance(event, InstrumentEvent):
            raise TypeError(f"event must be an InstrumentEvent, got {type(event).__name__}")
        self._callbacks[event].append(callback)

    def on_any(self, callback: Callable[[InstrumentEvent, Any], None]) -> None:
        """Register a wildcard callback invoked for *every* event.

        The callback receives ``(event, payload)``.
        """
        self._any.append(callback)

    # ── Dispatch ──────────────────────────────────────────────────────

    def emit(self, event: InstrumentEvent, payload: Any) -> None:
        """Invoke all callbacks for ``event`` (plus wildcard callbacks).

        If an :class:`EventBusPort` was injected, the event is also
        published to it via ``bus.publish(DomainEvent.now(str(event), payload))``.

        A single failing listener never aborts dispatch; the error is
        logged and dispatch continues.
        """
        if not isinstance(event, InstrumentEvent):
            raise TypeError(f"event must be an InstrumentEvent, got {type(event).__name__}")

        # Snapshot to tolerate registration changes during dispatch.
        handlers = list(self._callbacks.get(event, []))
        wildcards = list(self._any)

        for cb in handlers:
            try:
                cb(payload)
            except Exception as exc:  # noqa: BLE001 - isolate listener failures
                warnings.warn(
                    f"EventHooks listener for {event.value!r} raised: {exc!r}",
                    RuntimeWarning,
                    stacklevel=2,
                )
                _log.exception("EventHooks listener for %s failed", event.value)

        for cb in wildcards:
            try:
                cb(event, payload)
            except Exception as exc:  # noqa: BLE001 - isolate listener failures
                warnings.warn(
                    f"EventHooks on_any listener raised for {event.value!r}: {exc!r}",
                    RuntimeWarning,
                    stacklevel=2,
                )
                _log.exception("EventHooks on_any listener failed for %s", event.value)

        if self._bus is not None:
            try:
                self._bus.publish(DomainEvent.now(event.value, payload))
            except Exception as exc:  # noqa: BLE001 - bus failures must not break dispatch
                warnings.warn(
                    f"EventHooks bus publish for {event.value!r} raised: {exc!r}",
                    RuntimeWarning,
                    stacklevel=2,
                )
                _log.exception("EventHooks failed to publish %s to bus", event.value)

    # ── Lifecycle ─────────────────────────────────────────────────────

    def clear(self, event: InstrumentEvent | None = None) -> None:
        """Clear callbacks.

        ``clear(None)`` clears everything (all events and wildcards).
        ``clear(event)`` clears only that event's callbacks.
        """
        if event is None:
            for ev in self._callbacks:
                self._callbacks[ev] = []
            self._any = []
            return
        if not isinstance(event, InstrumentEvent):
            raise TypeError(f"event must be an InstrumentEvent or None, got {type(event).__name__}")
        self._callbacks[event] = []

    def listener_count(self, event: InstrumentEvent | None = None) -> int:
        """Return the number of callbacks for ``event``.

        If ``event`` is ``None``, returns the total across all events
        plus the wildcard listeners.
        """
        if event is None:
            return sum(len(cbs) for cbs in self._callbacks.values()) + len(self._any)
        if not isinstance(event, InstrumentEvent):
            raise TypeError(f"event must be an InstrumentEvent or None, got {type(event).__name__}")
        return len(self._callbacks[event])
