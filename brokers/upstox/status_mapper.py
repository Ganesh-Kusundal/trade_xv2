"""Upstox order status mapper — translates Upstox-specific status strings to canonical.

Extends :data:`brokers.common.status_mapper.COMMON_STATUS_MAP` with
Upstox-specific status strings that have no Dhan equivalent.
"""

from __future__ import annotations

from brokers.common.core.domain import OrderStatus
from brokers.common.status_mapper import COMMON_STATUS_MAP, StatusMapperRegistry

UPSTOX_STATUS_MAP: dict[str, OrderStatus] = {
    **COMMON_STATUS_MAP,
    # Upstox-specific additions
    "OPEN_ORDER": OrderStatus.OPEN,
    "TRIGGER_ORDER": OrderStatus.OPEN,
    "CANCEL_PENDING": OrderStatus.CANCELLED,
    "REJECTED_BY_BROKER": OrderStatus.REJECTED,
    "REJECTED_BY_EXCHANGE": OrderStatus.REJECTED,
    "MODIFIED": OrderStatus.OPEN,
    "MODIFIED_PENDING": OrderStatus.OPEN,
}

# Register Upstox mappings at module load
StatusMapperRegistry.register("upstox", UPSTOX_STATUS_MAP)


def normalize_upstox_status(broker_status: str) -> OrderStatus:
    """Map an Upstox-specific status string to canonical OrderStatus."""
    normalized = broker_status.upper().strip().replace(" ", "_")
    return UPSTOX_STATUS_MAP.get(normalized, OrderStatus.normalize(normalized))
