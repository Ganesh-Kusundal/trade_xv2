"""Paper ExecutionProvider — adapts PaperGateway to the domain ExecutionProvider port."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from brokers.common.transport_errors import order_result_from_response
from domain.orders.requests import ModifyOrderRequest, OrderRequest
from domain.ports.order_placement import OrderPlacementPort, invoke_place_order
from domain.ports.protocols import ExecutionProvider, OrderResult


class PaperExecutionProvider(ExecutionProvider):
    """Adapts ``PaperGateway`` order/portfolio methods to ``ExecutionProvider``.

    Mirrors the live broker transport adapters so the OMS submit_fn can place
    paper orders through the same domain ExecutionProvider port (Wave C spine).
    """

    def __init__(self, gateway: OrderPlacementPort) -> None:
        self._gateway = gateway

    @property
    def name(self) -> str:
        return "paper"

    @staticmethod
    def _enum_value(value: Any) -> Any:
        return value.value if hasattr(value, "value") else value

    def place_order(self, request: OrderRequest) -> OrderResult:
        try:
            response = invoke_place_order(self._gateway, request)
        except Exception as exc:  # transport boundary: never raise into domain
            return OrderResult.fail(str(exc))
        return order_result_from_response(response)

    def cancel_order(self, order_id: str) -> OrderResult:
        try:
            return order_result_from_response(self._gateway.cancel_order(order_id))
        except Exception as exc:
            return OrderResult.fail(str(exc))

    def modify_order(self, request: ModifyOrderRequest) -> OrderResult:
        try:
            kwargs: dict[str, Any] = {}
            if request.quantity is not None:
                kwargs["quantity"] = request.quantity
            if request.price is not None:
                kwargs["price"] = request.price
            if request.trigger_price is not None:
                kwargs["trigger_price"] = request.trigger_price
            if request.order_type is not None:
                kwargs["order_type"] = self._enum_value(request.order_type)
            if request.validity is not None:
                kwargs["validity"] = self._enum_value(request.validity)
            if request.product_type is not None:
                kwargs["product_type"] = self._enum_value(request.product_type)
            return order_result_from_response(
                self._gateway.modify_order(request.order_id, **kwargs)
            )
        except Exception as exc:
            return OrderResult.fail(str(exc))

    def get_order_book(self) -> list:
        return self._gateway.get_orderbook()

    def get_positions(self) -> list:
        return self._gateway.positions()

    def get_holdings(self) -> list:
        return self._gateway.holdings()

    def get_funds(self) -> Any:
        return self._gateway.funds()
