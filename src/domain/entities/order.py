"""Order-related domain entities."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from domain.types import (
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)


class FieldMapping(Protocol):
    """Broker-specific field name mapping for Order parsing.

    Implemented by :class:`domain.field_mapping.DefaultFieldMapping` and
    broker-specific adapters. Kept as a domain protocol so transport layers
    can normalize without depending on each other.
    """

    def map_order_id(self, data: dict) -> str: ...
    def map_symbol(self, data: dict) -> str: ...
    def map_exchange(self, data: dict) -> str: ...
    def map_side(self, data: dict) -> str: ...
    def map_order_type(self, data: dict) -> str: ...
    def map_status(self, data: dict) -> str: ...
    def map_quantity(self, data: dict) -> int: ...
    def map_filled_quantity(self, data: dict) -> int: ...
    def map_price(self, data: dict) -> str | None: ...
    def map_avg_price(self, data: dict) -> str | None: ...
    def map_reject_reason(self, data: dict) -> str: ...


@dataclass(slots=True, frozen=True)
class Order:
    """Canonical order — returned by every broker adapter."""

    order_id: str
    symbol: str
    exchange: str
    side: Side
    order_type: OrderType
    quantity: int
    filled_quantity: int = 0
    price: Decimal = Decimal("0")
    trigger_price: Decimal = Decimal("0")
    status: OrderStatus = OrderStatus.OPEN
    timestamp: datetime | None = None
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY
    avg_price: Decimal = Decimal("0")
    reject_reason: str = ""
    correlation_id: str | None = None
    instrument_id: str | None = None

    @property
    def average_price(self) -> Decimal:
        """Alias for avg_price — Dhan and some brokers use this name."""
        return self.avg_price

    @property
    def remaining_quantity(self) -> int:
        return max(self.quantity - self.filled_quantity, 0)

    @property
    def is_complete(self) -> bool:
        return self.status.is_terminal

    def with_status(self, status: OrderStatus) -> Order:
        """Return a new Order with the given status."""
        return replace(self, status=status)

    def with_fill(self, filled_quantity: int, avg_price: Decimal) -> Order:
        """Return a new Order with updated fill quantity and average fill price."""
        return replace(self, filled_quantity=filled_quantity, avg_price=avg_price)

    def with_price(self, price: Decimal) -> Order:
        """Return a new Order with the given price."""
        return replace(self, price=Decimal(str(price)))

    def with_quantity(self, quantity: int) -> Order:
        """Return a new Order with the given quantity."""
        return replace(self, quantity=quantity)

    def with_order_type(self, order_type: OrderType) -> Order:
        """Return a new Order with the given order type."""
        return replace(self, order_type=order_type)


@dataclass(slots=True, frozen=True)
class OrderAck:
    """Domain acknowledgement of an order write — no transport fields."""

    success: bool
    order_id: str = ""
    message: str = ""
    status: OrderStatus = OrderStatus.OPEN
    broker_order_id: str = ""
    error_code: str = ""
    latency_ms: float = 0.0


@dataclass(slots=True, frozen=True)
class OrderResponse:
    """Adapter-facing order write result.

    Domain consumers should use :meth:`to_ack` to drop transport forensics
    (``http_status`` / ``raw_payload``).
    """

    success: bool
    order_id: str = ""
    message: str = ""
    status: OrderStatus = OrderStatus.OPEN
    broker_order_id: str = ""
    error_code: str = ""
    http_status: int | None = None
    raw_payload: dict[str, Any] | None = None
    latency_ms: float = 0.0
    # Idempotency correlation_id the caller supplied (or one generated for
    # them). Was previously passed at construction by
    # brokers/dhan/execution/order_placement.py without being defined here,
    # raising TypeError on every Dhan place_order call -- the field was
    # missing, not the caller being wrong to want it on the response.
    correlation_id: str = ""

    @classmethod
    def ok(
        cls,
        order_id: str = "",
        message: str = "Success",
        status: OrderStatus = OrderStatus.OPEN,
        raw_payload: dict[str, Any] | None = None,
        http_status: int | None = 200,
        latency_ms: float = 0.0,
    ) -> OrderResponse:
        """Construct a successful response."""
        return cls(
            success=True,
            order_id=order_id,
            broker_order_id=order_id,
            message=message,
            status=status,
            http_status=http_status,
            raw_payload=raw_payload,
            latency_ms=latency_ms,
        )

    @classmethod
    def fail(
        cls,
        message: str,
        error_code: str = "",
        http_status: int | None = None,
        raw_payload: dict[str, Any] | None = None,
        latency_ms: float = 0.0,
        status: OrderStatus = OrderStatus.REJECTED,
    ) -> OrderResponse:
        """Construct a failed response."""
        return cls(
            success=False,
            message=message,
            status=status,
            error_code=error_code,
            http_status=http_status,
            raw_payload=raw_payload,
            latency_ms=latency_ms,
        )

    def with_broker_id(self, broker_id: str) -> OrderResponse:
        """Return a copy with ``broker_order_id`` populated."""
        return replace(self, broker_order_id=broker_id)

    def to_ack(self) -> OrderAck:
        """Strip transport forensics for domain consumers."""
        return OrderAck(
            success=self.success,
            order_id=self.order_id,
            message=self.message,
            status=self.status,
            broker_order_id=self.broker_order_id,
            error_code=self.error_code,
            latency_ms=self.latency_ms,
        )
