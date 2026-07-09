"""Aggregate Roots — the entry points to domain consistency boundaries.

Each Aggregate Root owns identity and state, delegates behavior to
providers and services, and enforces invariants within its boundary.

Submodules:
    instrument.py — InstrumentAggregate (replaces the anemic Instrument entity)
    order.py — OrderAggregate (order lifecycle + trades)
    position.py — PositionAggregate (account + instrument position state)
    account.py — AccountAggregate (balance + fund limits)
"""

from __future__ import annotations

from domain.aggregates.account import AccountAggregate
from domain.aggregates.instrument import InstrumentAggregate
from domain.aggregates.order import OrderAggregate
from domain.aggregates.position import PositionAggregate

__all__ = [
    "AccountAggregate",
    "InstrumentAggregate",
    "OrderAggregate",
    "PositionAggregate",
]
