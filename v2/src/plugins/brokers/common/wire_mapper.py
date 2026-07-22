"""WireMapper — convert between domain types and broker wire format."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from domain.entities import Order
from domain.enums import OrderSide, OrderStatus, OrderType
from domain.messages import OrderCommand
from domain.value_objects import InstrumentId, OrderId, Price, Quantity


@dataclass(frozen=True, slots=True)
class WireMapper:
    """Maps domain OrderCommand ↔ broker wire dicts.

    ``field_map`` renames domain fields to broker field names.
    ``side_map`` / ``order_type_map`` translate enum values.
    ``status_map`` translates broker status strings to OrderStatus values.
    """

    field_map: dict[str, str] = field(default_factory=dict)
    side_map: dict[OrderSide, str] = field(default_factory=dict)
    order_type_map: dict[OrderType, str] = field(default_factory=dict)
    status_map: dict[str, OrderStatus] = field(default_factory=dict)

    def to_wire(self, cmd: OrderCommand, symbol: str) -> dict[str, Any]:
        fm = self.field_map
        wire: dict[str, Any] = {}
        wire[fm.get("symbol", "symbol")] = symbol
        wire[fm.get("side", "side")] = self.side_map.get(cmd.side, cmd.side.value)
        wire[fm.get("order_type", "order_type")] = self.order_type_map.get(
            cmd.order_type, cmd.order_type.value
        )
        wire[fm.get("quantity", "quantity")] = int(cmd.quantity.value)
        if cmd.price is not None:
            wire[fm.get("price", "price")] = float(cmd.price.value)
        wire[fm.get("time_in_force", "time_in_force")] = cmd.time_in_force.value
        return wire

    def from_wire(self, data: dict[str, Any]) -> Order:
        fm = self.field_map
        inv_side = {v: k for k, v in self.side_map.items()}
        inv_type = {v: k for k, v in self.order_type_map.items()}

        raw_side = data[fm.get("side", "side")]
        side = inv_side.get(raw_side, OrderSide(raw_side))

        raw_type = data[fm.get("order_type", "order_type")]
        order_type = inv_type.get(raw_type, OrderType(raw_type))

        raw_status = data.get(fm.get("status", "status"), "")
        status = self.status_map.get(raw_status, OrderStatus(raw_status))

        raw_price = data.get(fm.get("price", "price"))
        price = Price(Decimal(str(raw_price))) if raw_price is not None else None

        return Order(
            order_id=OrderId(str(data[fm.get("order_id", "order_id")])),
            instrument_id=InstrumentId(str(data[fm.get("symbol", "symbol")])),
            side=side,
            order_type=order_type,
            quantity=Quantity(Decimal(str(data[fm.get("quantity", "quantity")]))),
            price=price,
            time_in_force="DAY",
            status=status,
            correlation_id=None,  # type: ignore[arg-type]
        )
