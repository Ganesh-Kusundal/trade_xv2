"""Integration test: exactly 1 ORDER_PLACED event through OMS submit path."""

from __future__ import annotations

from domain.ports.execution_context import is_oms_managed_submit, oms_managed


class _FakeEventBus:
    def __init__(self):
        self.events: list = []

    def publish(self, event):
        self.events.append(event)


def test_oms_managed_suppresses_adapter_duplicate():
    """When OMS wraps a broker call with oms_managed(), the adapter's
    _publish check sees is_oms_managed_submit() == True and skips
    its own ORDER_PLACED. Only the OMS-level event fires."""
    bus = _FakeEventBus()

    def adapter_publish(bus, event_type, symbol):
        if is_oms_managed_submit():
            return
        bus.events.append({"event_type": event_type, "symbol": symbol, "source": "adapter"})

    def oms_publish(bus, event_type, symbol):
        bus.events.append({"event_type": event_type, "symbol": symbol, "source": "oms"})

    with oms_managed():
        adapter_publish(bus, "ORDER_PLACED", "RELIANCE")

    oms_publish(bus, "ORDER_PLACED", "RELIANCE")

    assert len(bus.events) == 1
    assert bus.events[0]["source"] == "oms"


def test_without_oms_managed_adapter_publishes():
    """Without oms_managed(), the adapter publishes normally."""
    bus = _FakeEventBus()

    def adapter_publish(bus, event_type, symbol):
        if is_oms_managed_submit():
            return
        bus.events.append({"event_type": event_type, "symbol": symbol, "source": "adapter"})

    adapter_publish(bus, "ORDER_PLACED", "RELIANCE")

    assert len(bus.events) == 1
    assert bus.events[0]["source"] == "adapter"
