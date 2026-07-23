"""Normalize venue quote dict → domain Quote."""

from __future__ import annotations

from typing import Any, Mapping

from domain.entities import Quote
from domain.value_objects import InstrumentId, Price, Quantity
from plugins.brokers.common.wire import BaseWireAdapter


def normalize_quote(data: Mapping[str, Any], *, instrument_id: InstrumentId) -> Quote:
    """Normalize venue quote dict to domain Quote with defensive parsing.

    Handles partial quotes (e.g., market closed) by defaulting missing fields to zero.
    """
    def _to_decimal(key: str, default: str = "0") -> Any:
        """Safely convert dict value to Decimal, returning default on error."""
        import decimal
        try:
            return BaseWireAdapter.to_decimal(data.get(key, default))
        except (ValueError, TypeError, KeyError, decimal.InvalidOperation):
            return BaseWireAdapter.to_decimal(default)

    # Safely parse timestamp
    ts_raw = data.get("timestamp")
    ts = None
    if ts_raw is not None:
        try:
            ts = BaseWireAdapter.to_datetime(ts_raw)
        except (ValueError, TypeError):
            ts = None

    return Quote(
        instrument_id=instrument_id,
        bid=Price(value=_to_decimal("bid")),
        ask=Price(value=_to_decimal("ask")),
        bid_size=Quantity(value=_to_decimal("bid_size")),
        ask_size=Quantity(value=_to_decimal("ask_size")),
        timestamp=ts,
    )
