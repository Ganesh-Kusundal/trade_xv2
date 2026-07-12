"""Command contracts for the CQRS CommandDispatcher (ADR-012).

A Command is a plain intent object. It carries no behavior and never mutates
state. The dispatcher routes it to a handler, which delegates to the existing
domain services (``OrderManager``, subscription manager, historical-data
coordinator). Commands may produce a domain event via ``to_event()``, but the
event is published by the dispatcher *after* the handler returns — the bus is
the async fan-out, never the return path.

Design rules (enforced by import-linter "Dispatcher broker isolation"):
- Commands live in ``runtime.commands`` and depend only on ``domain``.
- Commands MUST NOT import ``brokers.*`` or ``infrastructure`` (except ports).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from domain.enums import OrderType, ProductType, Side


@dataclass(frozen=True)
class Command(ABC):
    """Abstract base for all commands routed by :class:`CommandDispatcher`."""

    correlation_id: str

    @property
    @abstractmethod
    def command_type(self) -> str:
        """Stable routing key used by the dispatcher to select a handler."""
        ...


@dataclass(frozen=True)
class PlaceOrderCommand(Command):
    """Intent to place an order through the OMS.

    Wraps the canonical ``OmsOrderCommand`` so the dispatcher owns routing and
    idempotency correlation, while ``OrderManager`` keeps ownership of the
    order lifecycle, risk check, and broker I/O.
    """

    symbol: str
    exchange: str
    side: Side
    quantity: int
    price: Decimal = Decimal("0")
    order_type: OrderType = OrderType.MARKET
    product_type: ProductType = ProductType.INTRADAY

    @property
    def command_type(self) -> str:
        return "place_order"

    def to_oms_command(self) -> Any:
        """Build the canonical OMS command (avoids a hard import cycle)."""
        from application.oms.order_manager import OmsOrderCommand

        return OmsOrderCommand(
            symbol=self.symbol,
            exchange=self.exchange,
            side=self.side,
            quantity=self.quantity,
            price=self.price,
            order_type=self.order_type,
            product_type=self.product_type,
            correlation_id=self.correlation_id,
        )


@dataclass(frozen=True)
class SubscribeInstrumentCommand(Command):
    """Intent to subscribe to a live instrument feed."""

    instrument_id: str
    mode: str = "market"

    @property
    def command_type(self) -> str:
        return "subscribe_instrument"


@dataclass(frozen=True)
class LoadHistoryCommand(Command):
    """Intent to load historical series for an instrument."""

    symbol: str
    timeframe: str = "1m"
    lookback: int = 300

    @property
    def command_type(self) -> str:
        return "load_history"


@dataclass(frozen=True)
class CommandResult:
    """Synchronous result returned by the dispatcher (never via the bus).

    Mirrors the shape of ``OmsOrderCommand`` results so callers (SDK/CLI/API)
    get a uniform return value regardless of which handler ran.
    """

    success: bool
    data: Any | None = None
    error: str | None = None
    correlation_id: str | None = None
    event: Any | None = field(default=None, repr=False)
