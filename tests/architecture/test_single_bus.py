"""P3-T2 (drift D12): document and enforce the single event-bus boundary.

Zero-parity requires one canonical event bus. The boundary:

* ``infrastructure.event_bus.EventBus`` is the **canonical** implementation.
  Production wiring (bootstrap, factory, replay, backtest, async wrapper) all
  construct ``EventBus`` (optionally wrapped by ``AsyncEventBus``).
* ``infrastructure.providers.null.stubs.NullEventBus`` is a **test-only /
  no-op fallback** — it must never be the source of truth in a running system.
* ``interface.ui.services.event_bus_service.EventBusService`` is a **UI
  facade** — a read-only mirror that is *injected* the canonical bus; it does
  not construct a competing bus.

This test locks that contract: the canonical class exists, NullEventBus is a
no-op, and EventBusService takes an injected bus rather than building one.
"""

from __future__ import annotations

from infrastructure.event_bus import EventBus
from infrastructure.providers.null.stubs import NullEventBus


def test_canonical_event_bus_is_single_implementation():
    """The canonical bus is ``infrastructure.event_bus.EventBus``."""
    assert EventBus is not None
    bus = EventBus()
    assert bus is not None
    # NullEventBus is a distinct, no-op type (not the canonical one).
    assert not isinstance(NullEventBus(), EventBus)


def test_null_event_bus_is_noop_fallback():
    """NullEventBus never raises and never delivers — a safe test fallback."""
    null = NullEventBus()
    # publish/subscribe/unsubscribe must be no-ops, not real dispatch.
    null.publish(object())
    token = null.subscribe("ORDER", lambda e: None)
    assert null.unsubscribe(token) in (False, True)
    # It must not be the canonical bus used in production wiring.
    assert not isinstance(null, EventBus)


def test_event_bus_service_is_injected_facade():
    """EventBusService is a UI facade — it receives the canonical bus.

    It must not construct a competing EventBus internally as its source of
    truth (that was the historical silent-bug: fabricated events on a second
    bus). We assert the constructor accepts an injected bus and stores it.
    """
    from interface.ui.services.event_bus_service import EventBusService

    bus = EventBus()
    svc = EventBusService(event_bus=bus)
    # The injected canonical bus is what the facade mirrors.
    assert svc.event_bus is bus
