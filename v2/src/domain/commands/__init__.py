"""Order commands — frozen; PlaceOrderCommand requires correlation_id."""

from __future__ import annotations

from dataclasses import dataclass

from domain.enums import OrderSide, OrderType, ProductType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, OrderId, Price, Quantity


@dataclass(frozen=True, slots=True)
class PlaceOrderCommand:
    instrument_id: InstrumentId
    side: OrderSide
    order_type: OrderType
    quantity: Quantity
    price: Price | None
    time_in_force: TimeInForce
    correlation_id: CorrelationId
    product_type: ProductType | None = None
    trigger_price: Price | None = None
    disclosed_quantity: Quantity | None = None
    market_protection: int | None = None

    def __post_init__(self) -> None:
        if self.correlation_id is None:
            raise ValueError("correlation_id is mandatory on PlaceOrderCommand")


@dataclass(frozen=True, slots=True)
class CancelOrderCommand:
    order_id: OrderId
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ModifyOrderCommand:
    order_id: OrderId
    new_quantity: Quantity | None = None
    new_price: Price | None = None
