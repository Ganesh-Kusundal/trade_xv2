"""Routing policy port — broker selection for order routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from domain.enums import BrokerId, ExchangeId
from domain.value_objects import InstrumentId


@runtime_checkable
class RoutingPolicy(Protocol):
    def route(self, instrument_id: InstrumentId) -> BrokerId: ...


@dataclass(frozen=True, slots=True)
class RoutingRule:
    """Maps an exchange to a preferred broker."""

    exchange: ExchangeId
    broker: BrokerId
