"""Upstox wire adapter — declarative broker-varying policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from brokers.common.acl import normalize_order_status
from domain import OrderStatus
from domain.constants.exchanges import CDS, MCX, NFO, NSE


@dataclass(frozen=True)
class UpstoxWireAdapter:
    broker_id: str = "upstox"
    rest_base: str = "https://api.upstox.com"
    status_map: dict[str, OrderStatus] = field(default_factory=dict)
    exchange_aliases: dict[str, str] = field(
        default_factory=lambda: {
            NSE: "NSE_EQ",
            NFO: "NSE_FO",
            MCX: "MCX_FO",
            CDS: "NCD_FO",
        }
    )

    def normalize_status(self, raw: object | None) -> OrderStatus:
        return normalize_order_status(raw)

    def price_from_wire(self, value: Any) -> Decimal:
        return Decimal(str(value or 0))

    def price_to_wire(self, value: Decimal) -> float:
        return float(value)

    def strategy_for(self, feature: str) -> str:
        return f"upstox.{feature}"


def build_upstox_wire() -> UpstoxWireAdapter:
    return UpstoxWireAdapter()


__all__ = ["UpstoxWireAdapter", "build_upstox_wire"]
