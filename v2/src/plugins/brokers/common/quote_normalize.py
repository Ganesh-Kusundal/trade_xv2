"""Normalize venue quote dict → domain Quote."""

from __future__ import annotations

from typing import Any, Mapping

from domain.entities import Quote
from domain.value_objects import InstrumentId, Price, Quantity
from plugins.brokers.common.wire import BaseWireAdapter


def normalize_quote(data: Mapping[str, Any], *, instrument_id: InstrumentId) -> Quote:
    return Quote(
        instrument_id=instrument_id,
        bid=Price(value=BaseWireAdapter.to_decimal(data["bid"])),
        ask=Price(value=BaseWireAdapter.to_decimal(data["ask"])),
        bid_size=Quantity(value=BaseWireAdapter.to_decimal(data["bid_size"])),
        ask_size=Quantity(value=BaseWireAdapter.to_decimal(data["ask_size"])),
        timestamp=BaseWireAdapter.to_datetime(data["timestamp"]),
    )
