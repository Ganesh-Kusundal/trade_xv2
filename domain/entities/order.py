"""Order-related domain entities."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from domain.status_mapper import StatusMapperRegistry
from domain.types import (
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)


class FieldMapping(Protocol):
    """Broker-specific field name mapping for Order parsing.

    Implement this protocol to define how broker-specific API responses
    map to canonical Order fields. Each broker adapter should provide
    its own implementation.

    Example::

        from domain.field_mapping import DefaultFieldMapping
        mapping = DefaultFieldMapping()
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

    @classmethod
    def from_broker_dict(
        cls,
        d: dict,
        field_mapping: FieldMapping | None = None,
        exchange_resolver: Callable[[str], Any] | None = None,
    ) -> Order:
        """Construct a canonical Order from a broker-specific dict.

        Args:
            d: Broker-specific order dict
            field_mapping: Broker-specific field name mapping (optional)
            exchange_resolver: Optional function to convert exchange string to Exchange enum

        If field_mapping is None, uses default Dhan-compatible mapping for backward compatibility.
        """
        from domain.field_mapping import DefaultFieldMapping

        mapping = field_mapping or DefaultFieldMapping()

        order_id = mapping.map_order_id(d)
        symbol = mapping.map_symbol(d)
        raw_exchange = mapping.map_exchange(d)
        exchange = exchange_resolver(raw_exchange) if exchange_resolver else raw_exchange

        side_str = mapping.map_side(d)
        side = Side.BUY if side_str == "BUY" else Side.SELL

        ot_str = mapping.map_order_type(d)
        try:
            order_type = OrderType(ot_str)
        except ValueError:
            order_type = OrderType.MARKET

        status_str = mapping.map_status(d)
        status = StatusMapperRegistry.normalize(status_str)

        def _opt_dec(v: str | None) -> Decimal | None:
            if v in (None, ""):
                return None
            return Decimal(v)

        return cls(
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            order_type=order_type,
            quantity=mapping.map_quantity(d),
            filled_quantity=mapping.map_filled_quantity(d),
            price=_opt_dec(mapping.map_price(d)) or Decimal("0"),
            avg_price=_opt_dec(mapping.map_avg_price(d)) or Decimal("0"),
            status=status,
            reject_reason=mapping.map_reject_reason(d),
        )


@dataclass(slots=True, frozen=True)
class OrderResponse:
    """Canonical response from any order write operation.

    Used for ``place_order``, ``modify_order``, ``cancel_order``,
    ``place_slice_order`` and the corresponding delete operations.

    Invariants
    ----------
    * ``success`` MUST be ``True`` when the broker confirmed the action.
    * ``order_id`` is the **broker's** id when the broker returned one.
    * ``error_code`` is the canonical error code (string).
    * ``raw_payload`` is the broker's raw response body, kept verbatim
      for forensic / audit / reconciliation.
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
