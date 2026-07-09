"""Generic ExecutionProvider wrapping any gateway with place_order/cancel/modify."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from domain.orders.requests import ModifyOrderRequest, OrderRequest
from domain.ports.protocols import ExecutionProvider, OrderResult


class GatewayExecutionProvider(ExecutionProvider):
    """Adapts a broker gateway (duck-typed place_order) to ExecutionProvider.

    Used for Upstox (and any gateway) when a broker-specific transport is not
    registered. Dhan prefers :class:`brokers.dhan.transport.DhanOrderTransport`.
    """

    def __init__(self, gateway: Any, *, broker_id: str = "gateway") -> None:
        self._gateway = gateway
        self._broker_id = broker_id

    @property
    def name(self) -> str:
        return self._broker_id

    @staticmethod
    def _enum_value(value: Any) -> Any:
        return value.value if hasattr(value, "value") else value

    @staticmethod
    def _wrap(response: Any) -> OrderResult:
        if getattr(response, "success", True):
            return OrderResult.ok(response)
        return OrderResult.fail(
            getattr(response, "message", None)
            or getattr(response, "error", None)
            or "broker rejected order"
        )

    def place_order(self, request: OrderRequest) -> OrderResult:
        try:
            response = self._gateway.place_order(
                symbol=request.symbol or request.security_id,
                exchange=request.exchange,
                side=self._enum_value(request.transaction_type),
                quantity=request.quantity,
                price=request.price,
                order_type=self._enum_value(request.order_type),
                product_type=self._enum_value(request.product_type),
                validity=self._enum_value(request.validity),
                trigger_price=request.trigger_price or Decimal("0"),
                correlation_id=request.correlation_id,
            )
        except TypeError:
            # Some gateways use different kwargs — fall back to OrderRequest object
            try:
                response = self._gateway.place_order(request)
            except Exception as exc:
                return OrderResult.fail(str(exc))
        except Exception as exc:
            return OrderResult.fail(str(exc))
        return self._wrap(response)

    def cancel_order(self, order_id: str) -> OrderResult:
        try:
            return self._wrap(self._gateway.cancel_order(order_id))
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
            return self._wrap(self._gateway.modify_order(request.order_id, **kwargs))
        except Exception as exc:
            return OrderResult.fail(str(exc))

    def get_order_book(self) -> list:
        for name in ("get_orderbook", "get_order_book", "orders"):
            fn = getattr(self._gateway, name, None)
            if callable(fn):
                return list(fn() or [])
        return []

    def get_positions(self) -> list:
        fn = getattr(self._gateway, "positions", None)
        return list(fn() or []) if callable(fn) else []

    def get_holdings(self) -> list:
        fn = getattr(self._gateway, "holdings", None)
        return list(fn() or []) if callable(fn) else []

    def get_funds(self) -> Any:
        fn = getattr(self._gateway, "funds", None)
        return fn() if callable(fn) else None
