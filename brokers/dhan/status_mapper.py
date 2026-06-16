"""Dhan order status mapper — translates Dhan-specific status strings to canonical."""

from __future__ import annotations

from brokers.common.core.domain import OrderStatus

DHAN_STATUS_MAP: dict[str, OrderStatus] = {
    "EXECUTED": OrderStatus.FILLED,
    "COMPLETE": OrderStatus.FILLED,
    "TRADED": OrderStatus.FILLED,
    "TRANSIT": OrderStatus.OPEN,
    "TRIGGER_PENDING": OrderStatus.OPEN,
    "PENDING": OrderStatus.OPEN,
    "PLACED": OrderStatus.OPEN,
    "TRIGGERED": OrderStatus.OPEN,
    "OPEN_PENDING": OrderStatus.OPEN,
    "PUT_ORDER_REQ_RECEIVED": OrderStatus.OPEN,
    "PARTIAL": OrderStatus.PARTIALLY_FILLED,
    "PARTIALLY_EXECUTED": OrderStatus.PARTIALLY_FILLED,
    "PARTIALLY_CANCELLED": OrderStatus.PARTIALLY_FILLED,
    "AFTER_MARKET_ORDER_REQ_RECEIVED": OrderStatus.OPEN,
    "AMO": OrderStatus.OPEN,
    "MARGIN_TRADED": OrderStatus.PARTIALLY_FILLED,
    "CANCELLED": OrderStatus.CANCELLED,
    "REJECTED": OrderStatus.REJECTED,
}


def normalize_dhan_status(broker_status: str) -> OrderStatus:
    """Map a Dhan-specific status string to canonical OrderStatus."""
    normalized = broker_status.upper().strip().replace(" ", "_")
    return DHAN_STATUS_MAP.get(normalized, OrderStatus.normalize(normalized))
