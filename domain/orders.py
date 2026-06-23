"""Canonical order, trade, and response dataclasses.

Submodule of :mod:`domain.entities` — imported via the re-export facade.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from domain.enums import OrderStatus, OrderType, ProductType, Side, Validity
from domain.status_mapper import StatusMapperRegistry  # P2-Phase 2: Import for status normalization


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
        # P2-Phase 2: Use StatusMapperRegistry directly (fixed Clean Architecture violation)
        status = StatusMapperRegistry.normalize(status_str)

        def _opt_dec(v: str | None) -> Decimal | None:
            if v is None or v == "":
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
class Trade:
    """Canonical trade — returned by every broker adapter."""

    trade_id: str
    order_id: str
    symbol: str
    exchange: str
    side: Side
    quantity: int
    price: Decimal = Decimal("0")
    trade_value: Decimal = Decimal("0")
    timestamp: datetime | None = None
    product_type: ProductType = ProductType.INTRADAY
    correlation_id: str | None = None

    @property
    def value(self) -> Decimal:
        if self.trade_value > 0:
            return self.trade_value
        return self.price * Decimal(str(self.quantity))


@dataclass(slots=True, frozen=True)
class OrderResponse:
    """Canonical response from any order write operation.

    Used for ``place_order``, ``modify_order``, ``cancel_order``,
    ``place_slice_order`` and the corresponding delete operations. The
    previous design had each adapter returning a heterogeneous mix of
    ``bool``, ``dict`` and ``(broker_id, broker_msg)`` tuples, which
    forced the OMS to special-case success detection for each broker.

    Invariants
    ----------
    * ``success`` MUST be ``True`` when the broker confirmed the action.
      ``"pending"`` or ``"transit"`` are NOT success — the call must be
      retried. Callers that need a tri-state can use :attr:`status` and
      :class:`OrderStatus`.
    * ``order_id`` is the **broker's** id when the broker returned one.
      For modify/cancel, the original id of the affected order.
    * ``broker_order_id`` is an alias for ``order_id`` kept for callers
      that already used the older name; new code should use ``order_id``.
    * ``error_code`` is the canonical :class:`BrokerErrorCode` (string)
      and ``http_status`` is the wire status the broker returned; both
      are diagnostic only and must not be parsed for business logic.
    * ``raw_payload`` is the broker's raw response body, kept verbatim
      for forensic / audit / reconciliation. It is **not** part of the
      contract — schema differences across brokers are expected.
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
        """Construct a successful response.

        ``broker_order_id`` defaults to ``order_id`` so callers that only
        pass one argument do not have to duplicate it.
        """
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
        """Construct a failed response.

        ``error_code`` SHOULD be a :class:`BrokerErrorCode` string when
        the broker returned a recognisable error; otherwise the broker's
        own error code (e.g. ``"DH-906"``) is acceptable.
        """
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
        """Return a copy with ``broker_order_id`` populated.

        Useful when the response is created before the broker returns
        its native id (e.g. inside a retry wrapper).
        """
        return replace(self, broker_order_id=broker_id)


# ---------------------------------------------------------------------------
# Order Status Transitions (P2-Phase 2)
# ---------------------------------------------------------------------------

# Order state machine transition table
# Used by OrderManager to validate status updates
ORDER_STATUS_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.OPEN: frozenset({
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
        OrderStatus.EXPIRED,
    }),
    OrderStatus.PARTIALLY_FILLED: frozenset({
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
    }),
    OrderStatus.FILLED: frozenset(),  # Terminal
    OrderStatus.CANCELLED: frozenset(),  # Terminal
    OrderStatus.REJECTED: frozenset(),  # Terminal
    OrderStatus.EXPIRED: frozenset(),  # Terminal
}
