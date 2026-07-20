"""Generic ExecutionProvider wrapping any gateway with place_order/cancel/modify."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from domain.orders.requests import ModifyOrderRequest, OrderRequest
from domain.ports.protocols import ExecutionProvider, OrderResult
from infrastructure.resilience.transport_errors import order_result_from_response

logger = logging.getLogger(__name__)


class GatewayExecutionProvider(ExecutionProvider):
    """Adapts a broker gateway (duck-typed place_order) to ExecutionProvider.

    Used for Upstox (and any gateway) when a broker-specific transport is not
    registered. Dhan prefers :class:`brokers.dhan.api.transport.DhanOrderTransport`.
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
    def _allows_legacy_place_order_fallback(gateway: Any) -> bool:
        broker_id = str(getattr(gateway, "broker_id", "") or "").lower()
        return broker_id in {"paper", ""}

    def place_order(self, request: OrderRequest) -> OrderResult:
        try:
            response = self._gateway.place_order(
                symbol=request.symbol,
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
        except TypeError as exc:
            if self._allows_legacy_place_order_fallback(self._gateway):
                try:
                    response = self._gateway.place_order(request)
                except Exception as inner:
                    return OrderResult.fail(str(inner))
            else:
                logger.error(
                    "gateway_place_order_signature_mismatch broker=%s: %s",
                    self._broker_id,
                    exc,
                )
                return OrderResult.fail("gateway signature mismatch")
        except Exception as exc:
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
            return order_result_from_response(
                self._gateway.modify_order(request.order_id, **kwargs)
            )
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
