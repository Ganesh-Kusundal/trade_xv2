"""Aggregate Roots — the entry points to domain consistency boundaries.

Each Aggregate Root owns identity and state, delegates behavior to
providers and services, and enforces invariants within its boundary.

Submodules:
    position.py — PositionAggregate (account + instrument position state)
    account.py — AccountAggregate (balance + fund limits)

Order lifecycle is owned by application.oms.OrderManager (not a domain aggregate).
"""

from __future__ import annotations

from domain.aggregates.account import AccountAggregate
from domain.aggregates.position import PositionAggregate

__all__ = [
    "AccountAggregate",
    "PositionAggregate",
]
