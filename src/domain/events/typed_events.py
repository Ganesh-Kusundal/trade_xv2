"""Typed event wrappers for compile-time safety on critical OMS events.

Split from ``types.py`` (ADR-010) to reduce file size while maintaining
backward compatibility via re-exports in ``types.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from domain.entities.order import Order
    from domain.entities.trade import Trade

from domain.events.types import DomainEvent, EventType


@dataclass(frozen=True)
class TypedDomainEvent:
    """Base for typed event wrappers — delegates to the underlying DomainEvent."""

    underlying_event: Any  # DomainEvent (avoid circular import)

    @property
    def event_type(self) -> str:
        return self.underlying_event.event_type

    @property
    def event_id(self) -> str:
        return self.underlying_event.event_id

    @property
    def correlation_id(self) -> str | None:
        return self.underlying_event.correlation_id


@dataclass(frozen=True)
class OrderUpdatedEvent(TypedDomainEvent):
    """Typed wrapper for ORDER_UPDATED events."""

    order: Order = None  # type: ignore[assignment]

    @classmethod
    def from_domain_event(cls, event: Any) -> OrderUpdatedEvent:
        from domain.entities.order import Order

        order = event.payload.get("order")
        if not isinstance(order, Order):
            raise ValueError(
                f"ORDER_UPDATED event must contain Order object in payload, "
                f"got {type(order).__name__}"
            )
        return cls(order=order, underlying_event=event)


@dataclass(frozen=True)
class TradeFilledEvent(TypedDomainEvent):
    """Typed wrapper for TRADE events (broker fill received)."""

    trade: Trade = None  # type: ignore[assignment]

    @classmethod
    def from_domain_event(cls, event: Any) -> TradeFilledEvent:
        from domain.entities.trade import Trade

        trade = event.payload.get("trade")
        if not isinstance(trade, Trade):
            raise ValueError(
                f"TRADE event must contain Trade object in payload, "
                f"got {type(trade).__name__}"
            )
        return cls(trade=trade, underlying_event=event)


@dataclass(frozen=True)
class TradeAppliedEvent(TypedDomainEvent):
    """Typed wrapper for TRADE_APPLIED events (OMS accepted trade)."""

    trade: Trade = None  # type: ignore[assignment]

    @classmethod
    def from_domain_event(cls, event: Any) -> TradeAppliedEvent:
        from domain.entities.trade import Trade

        trade = event.payload.get("trade")
        if not isinstance(trade, Trade):
            raise ValueError(
                f"TRADE_APPLIED event must contain Trade object in payload, "
                f"got {type(trade).__name__}"
            )
        return cls(trade=trade, underlying_event=event)


@dataclass(frozen=True)
class ExecutionPlanBuiltEvent(TypedDomainEvent):
    """Typed wrapper for EXECUTION_PLAN_BUILT events."""

    execution_plan: Any = None  # domain.orders.execution_plan.ExecutionPlan

    @classmethod
    def from_domain_event(cls, event: Any) -> ExecutionPlanBuiltEvent:
        from domain.orders.execution_plan import ExecutionPlan

        plan = event.payload.get("execution_plan")
        if not isinstance(plan, ExecutionPlan):
            raise ValueError(
                f"EXECUTION_PLAN_BUILT event must contain ExecutionPlan object "
                f"in payload, got {type(plan).__name__}"
            )
        return cls(execution_plan=plan, underlying_event=event)


@dataclass(frozen=True)
class OrderRequestedEvent(TypedDomainEvent):
    """Typed wrapper for ORDER_REQUESTED events."""

    request: Any = None  # domain.orders.requests.OrderRequest

    @classmethod
    def from_domain_event(cls, event: Any) -> OrderRequestedEvent:
        from domain.orders.requests import OrderRequest

        request = event.payload.get("request")
        if not isinstance(request, OrderRequest):
            raise ValueError(
                f"ORDER_REQUESTED event must contain OrderRequest object in "
                f"payload, got {type(request).__name__}"
            )
        return cls(request=request, underlying_event=event)


@dataclass(frozen=True)
class OrderFilledEvent(TypedDomainEvent):
    """Typed wrapper for TRADE_FILLED / TRADE / TRADE_APPLIED events."""

    trade: Trade = None  # type: ignore[assignment]

    @classmethod
    def from_domain_event(cls, event: Any) -> OrderFilledEvent:
        from domain.entities.trade import Trade

        trade = event.payload.get("trade")
        if not isinstance(trade, Trade):
            raise ValueError(
                f"{event.event_type} event must contain Trade object in payload, "
                f"got {type(trade).__name__}"
            )
        return cls(trade=trade, underlying_event=event)


@dataclass(frozen=True)
class QuoteUpdatedEvent(TypedDomainEvent):
    """Typed wrapper for QUOTE_UPDATED events."""

    symbol: str = ""
    exchange: str = ""
    ltp: Any = None  # Decimal
    bid: Any = None  # Decimal | None
    ask: Any = None  # Decimal | None
    volume: Any = None  # int | None

    @classmethod
    def from_domain_event(cls, event: Any) -> QuoteUpdatedEvent:
        payload = event.payload
        symbol = payload.get("symbol")
        exchange = payload.get("exchange")
        ltp = payload.get("ltp")
        if not isinstance(symbol, str) or not isinstance(exchange, str) or ltp is None:
            raise ValueError(
                f"QUOTE_UPDATED event must contain symbol (str), exchange (str) "
                f"and ltp in payload; got symbol={type(symbol).__name__}, "
                f"exchange={type(exchange).__name__}, ltp={type(ltp).__name__}"
            )
        try:
            ltp_d = Decimal(str(ltp))
            bid_d = (
                Decimal(str(payload["bid"]))
                if payload.get("bid") is not None
                else None
            )
            ask_d = (
                Decimal(str(payload["ask"]))
                if payload.get("ask") is not None
                else None
            )
            volume = (
                int(payload["volume"])
                if payload.get("volume") is not None
                else None
            )
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError(
                f"QUOTE_UPDATED event has non-numeric price/volume values: {exc}"
            ) from exc
        return cls(
            symbol=symbol,
            exchange=exchange,
            ltp=ltp_d,
            bid=bid_d,
            ask=ask_d,
            volume=volume,
            underlying_event=event,
        )


@dataclass(frozen=True)
class PositionClosedEvent(TypedDomainEvent):
    """Typed wrapper for POSITION_CLOSED events."""

    symbol: str = ""
    realized_pnl: Any = None  # Decimal
    quantity: Any = None  # int | None
    avg_price: Any = None  # Decimal | None

    @classmethod
    def from_domain_event(cls, event: Any) -> PositionClosedEvent:
        payload = event.payload
        symbol = payload.get("symbol")
        realized_pnl = payload.get("realized_pnl")
        if not isinstance(symbol, str) or realized_pnl is None:
            raise ValueError(
                f"POSITION_CLOSED event must contain symbol (str) and "
                f"realized_pnl in payload; got symbol={type(symbol).__name__}, "
                f"realized_pnl={type(realized_pnl).__name__}"
            )
        try:
            pnl_d = Decimal(str(realized_pnl))
            quantity = (
                int(payload["quantity"])
                if payload.get("quantity") is not None
                else None
            )
            avg_price = (
                Decimal(str(payload["avg_price"]))
                if payload.get("avg_price") is not None
                else None
            )
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError(
                f"POSITION_CLOSED event has non-numeric quantity/price values: {exc}"
            ) from exc
        return cls(
            symbol=symbol,
            realized_pnl=pnl_d,
            quantity=quantity,
            avg_price=avg_price,
            underlying_event=event,
        )


# Dispatch table: EventType string -> typed wrapper.
_TYPED_EVENT_DISPATCH: dict[str, type[TypedDomainEvent]] = {
    EventType.TRADE_FILLED.value: OrderFilledEvent,
    EventType.TRADE.value: OrderFilledEvent,
    EventType.TRADE_APPLIED.value: OrderFilledEvent,
    EventType.QUOTE_UPDATED.value: QuoteUpdatedEvent,
    EventType.POSITION_CLOSED.value: PositionClosedEvent,
}


def to_typed_event(event: DomainEvent) -> DomainEvent | TypedDomainEvent:
    """Return a typed wrapper for *event* if one exists, else the original.

    Backward-compatible: unknown event types are returned unchanged.
    """
    wrapper = _TYPED_EVENT_DISPATCH.get(event.event_type)
    if wrapper is None:
        return event
    try:
        return wrapper.from_domain_event(event)
    except (ValueError, KeyError, TypeError):
        return event
