"""BrokerTranslator — anti-corruption layer at the broker port edge.

Every broker wire payload that becomes a domain entity must pass through
``normalize_order_status`` (or a broker-specific translator that calls it).
Raw status strings must not escape this boundary onto ``Order.order_status``.
"""

from __future__ import annotations

from typing import Protocol

from domain import OrderStatus


def normalize_order_status(raw: object | None) -> OrderStatus:
    """Normalize any broker status string/enum to ``OrderStatus``."""
    if isinstance(raw, OrderStatus):
        return raw
    if raw is None:
        return OrderStatus.UNKNOWN
    return OrderStatus.normalize(str(raw))


class BrokerTranslator(Protocol):
    """Protocol for broker-specific wire → domain translators."""

    def status(self, raw: object | None) -> OrderStatus: ...


class DefaultBrokerTranslator:
    """Shared translator — status normalization only."""

    def status(self, raw: object | None) -> OrderStatus:
        return normalize_order_status(raw)


__all__ = [
    "BrokerTranslator",
    "DefaultBrokerTranslator",
    "normalize_order_status",
]
