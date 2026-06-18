"""Dhan order status mapper — translates Dhan-specific status strings to canonical.

Extends :data:`brokers.common.status_mapper.COMMON_STATUS_MAP` with
Dhan-specific status strings that have no Upstox equivalent.
"""

from __future__ import annotations

from brokers.common.core.domain import OrderStatus
from brokers.common.status_mapper import COMMON_STATUS_MAP, StatusMapperRegistry

DHAN_STATUS_MAP: dict[str, OrderStatus] = {
    **COMMON_STATUS_MAP,
    # Dhan-specific additions
    "TRANSIT": OrderStatus.OPEN,
    "TRIGGER_PENDING": OrderStatus.OPEN,
    "PENDING": OrderStatus.OPEN,
    "PLACED": OrderStatus.OPEN,
    "TRIGGERED": OrderStatus.OPEN,
    "OPEN_PENDING": OrderStatus.OPEN,
    "PUT_ORDER_REQ_RECEIVED": OrderStatus.OPEN,
    "PARTIALLY_CANCELLED": OrderStatus.PARTIALLY_FILLED,
}

# Register Dhan mappings at module load
StatusMapperRegistry.register("dhan", DHAN_STATUS_MAP)


def normalize_dhan_status(broker_status: str) -> OrderStatus:
    """Map a Dhan-specific status string to canonical OrderStatus."""
    normalized = broker_status.upper().strip().replace(" ", "_")
    return DHAN_STATUS_MAP.get(normalized, OrderStatus.normalize(normalized))
