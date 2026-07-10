"""Dhan wire adapter — declarative broker-varying policy.

Endpoints, status maps, and price/feed decode hooks live here. Reconnect,
status normalization, and capability frozensets live in the kernel / domain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from brokers.common.acl import normalize_order_status
from domain import OrderStatus
from domain.constants.exchanges import CDS, MCX, NFO, NSE


@dataclass(frozen=True)
class DhanWireAdapter:
    """Thin declarative policy for the Dhan transport."""

    broker_id: str = "dhan"
    rest_base: str = "https://api.dhan.co"
    status_map: dict[str, OrderStatus] = field(default_factory=dict)
    exchange_aliases: dict[str, str] = field(
        default_factory=lambda: {
            NSE: "NSE_EQ",
            NFO: "NSE_FNO",
            MCX: "MCX_COMM",
            CDS: "NSE_CURRENCY",
        }
    )

    def normalize_status(self, raw: object | None) -> OrderStatus:
        return normalize_order_status(raw)

    def price_from_wire(self, value: Any) -> Decimal:
        """Dhan REST prices are rupees (not paise)."""
        return Decimal(str(value or 0))

    def price_to_wire(self, value: Decimal) -> float:
        return float(value)

    def strategy_for(self, feature: str) -> str:
        """Return the registry key for a feature strategy."""
        return f"dhan.{feature}"


def build_dhan_wire() -> DhanWireAdapter:
    return DhanWireAdapter()


__all__ = ["DhanWireAdapter", "build_dhan_wire"]
