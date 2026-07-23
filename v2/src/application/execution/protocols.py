"""Injectable protocols — prefer application.oms / application.risk when present."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from domain.commands import PlaceOrderCommand
from domain.entities import Order
from domain.value_objects import CorrelationId, OrderId

from application.risk.context import RiskCheckResult


@runtime_checkable
class RiskManager(Protocol):
    def check_order(
        self, command: PlaceOrderCommand, context: Any = None
    ) -> RiskCheckResult: ...


@runtime_checkable
class IdempotencyGuard(Protocol):
    def check_and_reserve(self, correlation_id: CorrelationId) -> Any: ...

    def record_result(self, correlation_id: CorrelationId, result: Any) -> None: ...


@runtime_checkable
class OrderStore(Protocol):
    def upsert(self, order: Order) -> None: ...

    def get(self, order_id: OrderId) -> Order | None: ...

    def get_by_correlation(self, correlation_id: CorrelationId) -> Order | None: ...

    def all_orders(self) -> list[Order]: ...


@runtime_checkable
class FillSource(Protocol):
    def submit(self, command: PlaceOrderCommand) -> Order: ...

    def cancel(self, order_id: OrderId) -> None: ...


@runtime_checkable
class MessageBusPort(Protocol):
    def publish(self, message: object) -> None: ...


@runtime_checkable
class BrokerOrderAdapter(Protocol):
    def submit_order(self, command: PlaceOrderCommand) -> Order | OrderId: ...

    def cancel_order(self, order_id: OrderId) -> None: ...
