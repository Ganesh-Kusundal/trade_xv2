"""Order-related domain entities.

Money/Quantity fields (TOS-P1-004): ``price``, ``avg_price``, ``trigger_price`` are
:class:`~domain.primitives.Money`; ``quantity`` / ``filled_quantity`` are
:class:`~domain.primitives.Quantity`. Construction accepts Decimal/int/str for
backward compatibility and coerces in ``__post_init__``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from domain.primitives import Money, Quantity
from domain.types import (
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)


def _as_money(value: Money | Decimal | int | float | str | None) -> Money:
    if value is None:
        return Money(0)
    if isinstance(value, Money):
        return value
    return Money(value)


def _as_quantity(value: Quantity | Decimal | int | float | str | None) -> Quantity:
    if value is None:
        return Quantity(0)
    if isinstance(value, Quantity):
        return value
    return Quantity(value)


class FieldMapping(Protocol):
    """Broker-specific field name mapping for Order parsing."""

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
    quantity: Quantity
    filled_quantity: Quantity = Quantity(0)
    price: Money = Money(0)
    trigger_price: Money = Money(0)
    status: OrderStatus = OrderStatus.OPEN
    timestamp: datetime | None = None
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY
    avg_price: Money = Money(0)
    reject_reason: str = ""
    correlation_id: str | None = None
    instrument_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantity", _as_quantity(self.quantity))
        object.__setattr__(self, "filled_quantity", _as_quantity(self.filled_quantity))
        object.__setattr__(self, "price", _as_money(self.price))
        object.__setattr__(self, "trigger_price", _as_money(self.trigger_price))
        object.__setattr__(self, "avg_price", _as_money(self.avg_price))

    @property
    def average_price(self) -> Decimal:
        """Decimal view of avg_price (legacy name)."""
        return self.avg_price.to_decimal()

    @property
    def price_money(self) -> Money:
        return self.price

    @property
    def avg_price_money(self) -> Money:
        return self.avg_price

    @property
    def quantity_vo(self) -> Quantity:
        return self.quantity

    @property
    def remaining_quantity(self) -> int:
        return max(int(self.quantity) - int(self.filled_quantity), 0)

    @property
    def is_complete(self) -> bool:
        return self.status.is_terminal

    def with_status(self, status: OrderStatus) -> Order:
        from domain.entities.order_lifecycle import ORDER_STATUS_TRANSITIONS
        from domain.state_machine import IllegalTransitionError

        allowed = ORDER_STATUS_TRANSITIONS.get(self.status, frozenset())
        if status != self.status and status not in allowed:
            raise IllegalTransitionError(self.status, status)
        return replace(self, status=status)

    def with_fill(
        self,
        filled_quantity: Quantity | int,
        avg_price: Money | Decimal,
    ) -> Order:
        return replace(
            self,
            filled_quantity=_as_quantity(filled_quantity),
            avg_price=_as_money(avg_price),
        )

    def with_price(self, price: Money | Decimal) -> Order:
        return replace(self, price=_as_money(price))

    def with_quantity(self, quantity: Quantity | int) -> Order:
        return replace(self, quantity=_as_quantity(quantity))

    def with_order_type(self, order_type: OrderType) -> Order:
        return replace(self, order_type=order_type)

    @classmethod
    def from_broker_dict(
        cls,
        d: dict,
        field_mapping: FieldMapping | None = None,
        exchange_resolver: Callable[[str], Any] | None = None,
    ) -> Order:
        """Construct a canonical Order from a broker-specific dict.

        Args:
            d: Broker-specific order dict.
            field_mapping: Broker-specific field name mapping. Defaults to
                :class:`~domain.field_mapping.DefaultFieldMapping`.
            exchange_resolver: Optional function converting the raw exchange
                string into the broker's Exchange representation.
        """
        from domain.field_mapping import DefaultFieldMapping
        from domain.status_mapper import StatusMapperRegistry

        mapping = field_mapping or DefaultFieldMapping()

        raw_exchange = mapping.map_exchange(d)
        exchange = exchange_resolver(raw_exchange) if exchange_resolver else raw_exchange

        side_str = mapping.map_side(d)
        side = Side.BUY if side_str == "BUY" else Side.SELL

        try:
            order_type = OrderType(mapping.map_order_type(d))
        except ValueError:
            order_type = OrderType.MARKET

        def _opt_money(v: str | None) -> Money | None:
            return None if v in (None, "") else Money(Decimal(v))

        return cls(
            order_id=mapping.map_order_id(d),
            symbol=mapping.map_symbol(d),
            exchange=exchange,
            side=side,
            order_type=order_type,
            quantity=mapping.map_quantity(d),
            filled_quantity=mapping.map_filled_quantity(d),
            price=_opt_money(mapping.map_price(d)) or Money(0),
            avg_price=_opt_money(mapping.map_avg_price(d)) or Money(0),
            status=StatusMapperRegistry.normalize(mapping.map_status(d)),
            reject_reason=mapping.map_reject_reason(d),
        )


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
    """Adapter-facing order write result."""

    success: bool
    order_id: str = ""
    message: str = ""
    status: OrderStatus = OrderStatus.OPEN
    broker_order_id: str = ""
    error_code: str = ""
    http_status: int | None = None
    raw_payload: dict[str, Any] | None = None
    latency_ms: float = 0.0
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
        return replace(self, broker_order_id=broker_id)

    def to_ack(self) -> OrderAck:
        return OrderAck(
            success=self.success,
            order_id=self.order_id,
            message=self.message,
            status=self.status,
            broker_order_id=self.broker_order_id,
            error_code=self.error_code,
            latency_ms=self.latency_ms,
        )
