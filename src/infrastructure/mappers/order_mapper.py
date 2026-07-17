"""Broker order field mapping and dict -> Order parsing.

Thin re-export of the canonical domain mapping. The single source of truth
for field parsing lives in ``domain.field_mapping`` and ``domain.entities.order``
(REF-3): this module used to carry a near-verbatim copy of ``DefaultFieldMapping``
that DIVERGED on the exchange default ("NSE" vs ``DEFAULT_EXCHANGE``). It now
delegates to the domain implementation so there is exactly one mapper.
"""

from __future__ import annotations

from typing import Any, Protocol

from domain.entities import FieldMapping, Order
from domain.field_mapping import DefaultFieldMapping


class FieldMapping(Protocol):  # pragma: no cover - back-compat alias
    """Back-compat alias for the domain FieldMapping protocol."""

    def map_order_id(self, data: dict) -> str: ...
    def map_symbol(self, data: dict) -> str: ...
    def map_exchange(self, data: dict) -> str: ...
    def map_side(self, data: dict) -> str: ...
    def map_order_type(self, data: dict) -> str: ...
    def map_status(self, data: dict) -> str: ...
    def map_quantity(self, data: dict) -> int: ...
    def map_filled_quantity(self, data: dict) -> int: ...
    def map_price(self, data: dict) -> str | None: ...
    def map_avg_price(self, data: dict) -> str | None: ...
    def map_reject_reason(self, data: dict) -> str: ...


def order_from_broker_dict(
    d: dict,
    field_mapping: FieldMapping | None = None,
    exchange_resolver: Any | None = None,
) -> Order:
    """Construct a canonical Order from a broker-specific dict.

    Delegates to the canonical ``Order.from_broker_dict`` in domain.
    """
    return Order.from_broker_dict(d, field_mapping=field_mapping, exchange_resolver=exchange_resolver)
