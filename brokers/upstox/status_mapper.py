"""Upstox order status mapper — translates Upstox-specific status strings to canonical."""

from __future__ import annotations

from brokers.common.core.domain import OrderStatus

UPSTOX_STATUS_MAP: dict[str, OrderStatus] = {
    "OPEN_ORDER": OrderStatus.OPEN,
    "TRIGGER_ORDER": OrderStatus.OPEN,
    "CANCEL_PENDING": OrderStatus.CANCELLED,
    "REJECTED_BY_BROKER": OrderStatus.REJECTED,
    "REJECTED_BY_EXCHANGE": OrderStatus.REJECTED,
    "MODIFIED": OrderStatus.OPEN,
    "MODIFIED_PENDING": OrderStatus.OPEN,
    "AFTER_MARKET_ORDER_REQ_RECEIVED": OrderStatus.OPEN,
    "AMO": OrderStatus.OPEN,
    "MARGIN_TRADED": OrderStatus.PARTIALLY_FILLED,
    "EXECUTED": OrderStatus.FILLED,
    "COMPLETE": OrderStatus.FILLED,
    "TRADED": OrderStatus.FILLED,
    "PARTIAL": OrderStatus.PARTIALLY_FILLED,
    "PARTIALLY_EXECUTED": OrderStatus.PARTIALLY_FILLED,
}


def normalize_upstox_status(broker_status: str) -> OrderStatus:
    """Map an Upstox-specific status string to canonical OrderStatus."""
    normalized = broker_status.upper().strip().replace(" ", "_")
    return UPSTOX_STATUS_MAP.get(normalized, OrderStatus.normalize(normalized))
