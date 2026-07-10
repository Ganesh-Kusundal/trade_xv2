"""Unit tests for the standalone EventHooks system."""

from __future__ import annotations

from domain.events.bus import DomainEventBus
from domain.instruments.event_hooks import EventHooks, InstrumentEvent


class _StubBus(DomainEventBus):
    def __init__(self) -> None:
        self.published: list[tuple[str, object]] = []

    def publish(self, event_type: str, payload: dict) -> None:
        self.published.append((event_type, payload))

    def subscribe(self, event_type: str, handler) -> None:
        raise NotImplementedError

    def unsubscribe(self, event_type: str, handler) -> None:
        raise NotImplementedError


def test_register_and_emit():
    hooks = EventHooks()
    received: list[object] = []
    hooks.register(InstrumentEvent.TICK, received.append)
    hooks.emit(InstrumentEvent.TICK, {"price": 10})
    assert received == [{"price": 10}]


def test_on_any_wildcard():
    hooks = EventHooks()
    seen: list[tuple[InstrumentEvent, object]] = []
    hooks.on_any(lambda ev, pl: seen.append((ev, pl)))
    hooks.register(InstrumentEvent.QUOTE, lambda pl: None)
    hooks.emit(InstrumentEvent.QUOTE, "q")
    hooks.emit(InstrumentEvent.DEPTH, "d")
    assert seen == [
        (InstrumentEvent.QUOTE, "q"),
        (InstrumentEvent.DEPTH, "d"),
    ]


def test_listener_count():
    hooks = EventHooks()
    assert hooks.listener_count() == 0
    hooks.register(InstrumentEvent.TICK, lambda pl: None)
    hooks.register(InstrumentEvent.TICK, lambda pl: None)
    hooks.register(InstrumentEvent.QUOTE, lambda pl: None)
    hooks.on_any(lambda ev, pl: None)
    assert hooks.listener_count(InstrumentEvent.TICK) == 2
    assert hooks.listener_count(InstrumentEvent.QUOTE) == 1
    assert hooks.listener_count() == 4  # 2 + 1 + 1 wildcard


def test_clear():
    hooks = EventHooks()
    hooks.register(InstrumentEvent.TICK, lambda pl: None)
    hooks.register(InstrumentEvent.QUOTE, lambda pl: None)
    hooks.on_any(lambda ev, pl: None)
    hooks.clear(InstrumentEvent.TICK)
    assert hooks.listener_count(InstrumentEvent.TICK) == 0
    assert hooks.listener_count(InstrumentEvent.QUOTE) == 1
    hooks.clear()
    assert hooks.listener_count() == 0


def test_bad_callback_does_not_break_emit():
    hooks = EventHooks()
    received: list[object] = []
    good = lambda pl: received.append(pl)
    bad = lambda pl: (_ for _ in ()).throw(RuntimeError("boom"))
    hooks.register(InstrumentEvent.TICK, bad)
    hooks.register(InstrumentEvent.TICK, good)
    hooks.emit(InstrumentEvent.TICK, "payload")
    assert received == ["payload"]


def test_emits_to_injected_bus():
    bus = _StubBus()
    hooks = EventHooks(bus=bus)
    hooks.register(InstrumentEvent.TRADE, lambda pl: None)
    hooks.emit(InstrumentEvent.TRADE, {"qty": 5})
    assert bus.published == [("trade", {"qty": 5})]


def test_type_guard_on_register_and_emit():
    hooks = EventHooks()
    import pytest

    with pytest.raises(TypeError):
        hooks.register("tick", lambda pl: None)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        hooks.emit("tick", {})  # type: ignore[arg-type]
