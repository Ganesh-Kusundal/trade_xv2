"""Value Objects — immutable, identity-less domain primitives.

All value objects follow these rules:
- Frozen dataclasses (immutable after creation)
- Defined by attribute values, not identity
- Equality based on all attributes
- No side effects on construction

Submodules:
    state.py     — InstrumentState, SubscriptionState
    capability.py — Capability, ExtensionInfo
    money.py     — Money, TickSize
    price.py     — snap_to_tick, is_tick_aligned, to_wire_float
"""

from __future__ import annotations

from domain.value_objects.capability import Capability, ExtensionInfo
from domain.value_objects.money import Money, TickSize
from domain.value_objects.price import is_tick_aligned, snap_to_tick, to_wire_float
from domain.value_objects.state import InstrumentState, SubscriptionState

__all__ = [
    "Capability",
    "ExtensionInfo",
    "InstrumentState",
    "Money",
    "SubscriptionState",
    "TickSize",
    "is_tick_aligned",
    "snap_to_tick",
    "to_wire_float",
]
