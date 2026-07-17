"""DhanTransport — domain ports over the Dhan gateway facade (transport).

``DhanOrderTransport`` / ``DhanTransport`` wrap ``DhanWireAdapter`` so OMS and
Instrument code depend on ``ExecutionProvider`` / ``BrokerTransport``, not the
gateway class. The gateway remains as ops transport (Wave C — evolutionary).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from domain.capabilities import Capability
from domain.orders.requests import OrderRequest
from domain.ports.broker_transport import BrokerTransport
from domain.ports.protocols import ExecutionProvider, OrderResult


_DHAN_CAPABILITIES: tuple[Capability, ...] = (
    Capability.MARKET_DATA,
    Capability.ORDER_COMMAND,
    Capability.ORDER_QUERY,
    Capability.PORTFOLIO,
    Capability.OPTIONS_CHAIN,
    Capability.FUTURES,
    Capability.HISTORICAL_DATA,
    Capability.WEBSOCKET,
    Capability.DEPTH,
    Capability.ORDER_STREAM,
    Capability.OPTION_GREEKS,
    Capability.MARGIN,
    Capability.SLICE_ORDER,
    Capability.IDEMPOTENCY,
    Capability.EXIT_ALL,
)


class DhanOrderTransport(ExecutionProvider):
    """Adapts DhanWireAdapter order methods to the domain ExecutionProvider port."""

    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway

    @property
    def name(self) -> str:
        return "dhan"

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
                symbol=request.symbol,
                exchange=request.exchange,
                side=request.transaction_type.value,
                quantity=request.quantity,
                price=request.price,
                order_type=request.order_type.value,
                product_type=request.product_type.value,
                validity=request.validity.value,
                trigger_price=request.trigger_price or Decimal("0"),
                correlation_id=request.correlation_id,
            )
        except Exception as exc:  # transport boundary: never raise into domain
            return OrderResult.fail(str(exc))
        return self._wrap(response)

    def cancel_order(self, order_id: str) -> OrderResult:
        try:
            return self._wrap(self._gateway.cancel_order(order_id))
        except Exception as exc:
            return OrderResult.fail(str(exc))

    def modify_order(self, request) -> OrderResult:
        try:
            return self._wrap(
                self._gateway.modify_order(request.order_id, price=request.price, quantity=request.quantity)
            )
        except Exception as exc:
            return OrderResult.fail(str(exc))

    def get_order_book(self):
        return self._gateway.get_orderbook()

    def get_positions(self):
        return self._gateway.positions()

    def get_holdings(self):
        return self._gateway.holdings()

    def get_funds(self):
        return self._gateway.funds()


class DhanTransport(BrokerTransport):
    """Concrete Dhan broker plugin behind the domain BrokerTransport port."""

    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway
        self._market = gateway  # BrokerAdapter satisfies DataProvider structurally
        self._execution = DhanOrderTransport(gateway)

    @property
    def name(self) -> str:
        return "dhan"

    @property
    def market_data(self):
        return self._market

    @property
    def execution(self):
        return self._execution

    def capabilities(self) -> list[Capability]:
        return list(_DHAN_CAPABILITIES)

    def supports(self, cap: Capability) -> bool:
        return cap in _DHAN_CAPABILITIES

    def close(self) -> None:
        try:
            self._gateway.close()
        except Exception:
            pass
