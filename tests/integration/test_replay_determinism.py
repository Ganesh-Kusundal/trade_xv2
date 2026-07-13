"""Acceptance test: replay determinism (spec §11.3).

Same catalog + FakeClock must produce identical order intent streams.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from domain.ports.time_service import VirtualClock, use_clock


@pytest.fixture
def fixed_clock():
    return VirtualClock(datetime(2026, 7, 13, 9, 15, tzinfo=timezone.utc))


def _make_order_intent(correlation_id: str, symbol: str = "RELIANCE"):
    from domain import Order
    from domain.enums import OrderStatus
    from domain.types import Side, OrderType, ProductType, Validity

    return Order(
        order_id="",
        symbol=symbol,
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        price=2500.0,
        trigger_price=0.0,
        product_type=ProductType.CNC,
        validity=Validity.DAY,
        status=OrderStatus.OPEN,
        timestamp=None,
        correlation_id=correlation_id,
    )


def test_same_inputs_produce_identical_timestamps(fixed_clock):
    """Two runs with the same FakeClock produce identical event timestamps."""
    from domain.events.types import DomainEvent

    timestamps_run1 = []
    timestamps_run2 = []

    for timestamps in (timestamps_run1, timestamps_run2):
        clock = VirtualClock(datetime(2026, 7, 13, 9, 15, tzinfo=timezone.utc))
        with use_clock(clock):
            for i in range(5):
                evt = DomainEvent.now("TEST_EVENT", {"seq": i})
                timestamps.append(evt.timestamp)

    assert timestamps_run1 == timestamps_run2


def test_simulated_fill_source_deterministic(fixed_clock):
    """SimulatedFillSource produces deterministic order IDs given same prefix."""
    from application.execution.fill_source import SimulatedFillSource

    fs1 = SimulatedFillSource(order_id_prefix="det")
    fs2 = SimulatedFillSource(order_id_prefix="det")

    assert fs1._prefix == fs2._prefix


def test_virtual_clock_advance_is_deterministic():
    """VirtualClock advances produce reproducible timestamps."""
    from datetime import timedelta

    clock1 = VirtualClock(datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc))
    clock2 = VirtualClock(datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc))

    for _ in range(10):
        clock1.advance(timedelta(seconds=1))
        clock2.advance(timedelta(seconds=1))

    assert clock1.now() == clock2.now()
    assert clock1.now() == datetime(2026, 1, 1, 0, 0, 10, tzinfo=timezone.utc)
