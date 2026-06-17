"""Canonical status mapper — shared status string → OrderStatus mapping.

All broker-specific status mappers extend :data:`COMMON_STATUS_MAP`.
Entries that appear in both Upstox and Dhan status maps live here;
broker-specific status strings are added in each broker's own module.
"""

from __future__ import annotations

from brokers.common.core.domain import OrderStatus

COMMON_STATUS_MAP: dict[str, OrderStatus] = {
    # ── Terminal / filled ──
    "EXECUTED": OrderStatus.FILLED,
    "COMPLETE": OrderStatus.FILLED,
    "TRADED": OrderStatus.FILLED,
    # ── Partial fills ──
    "PARTIAL": OrderStatus.PARTIALLY_FILLED,
    "PARTIALLY_EXECUTED": OrderStatus.PARTIALLY_FILLED,
    "MARGIN_TRADED": OrderStatus.PARTIALLY_FILLED,
    # ── Open / pending ──
    "AFTER_MARKET_ORDER_REQ_RECEIVED": OrderStatus.OPEN,
    "AMO": OrderStatus.OPEN,
    # ── Terminal (non-fill) ──
    "CANCELLED": OrderStatus.CANCELLED,
    "REJECTED": OrderStatus.REJECTED,
}
