"""OrderService — orchestration wrapper for order execution.

Wraps a :class:`~domain.ports.protocols.ExecutionProvider` so the ``Instrument``
never talks to a broker directly for order operations.  Pure domain layer:
no broker or transport imports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from domain.orders.requests import ModifyOrderRequest, OrderRequest
    from domain.ports.protocols import ExecutionProvider


class OrderService:
    """Thin order-execution accessor over an :class:`ExecutionProvider` port."""

    def __init__(self, executor: ExecutionProvider | None = None) -> None:
        self._executor = executor

    @property
    def executor(self) -> ExecutionProvider | None:
        return self._executor

    def place_order(self, request: Any) -> Any:
        if self._executor is None:
            return None
        return self._executor.place_order(request)

    def cancel_order(self, order_id: str) -> Any:
        if self._executor is None:
            return None
        return self._executor.cancel_order(order_id)

    def modify_order(self, request: Any) -> Any:
        if self._executor is None:
            return None
        return self._executor.modify_order(request)

    def order_book(self) -> list:
        if self._executor is None:
            return []
        return self._executor.get_order_book()

    def positions(self) -> list:
        if self._executor is None:
            return []
        return self._executor.get_positions()

    def holdings(self) -> list:
        if self._executor is None:
            return []
        return self._executor.get_holdings()

    def funds(self) -> Any:
        if self._executor is None:
            return None
        return self._executor.get_funds()
