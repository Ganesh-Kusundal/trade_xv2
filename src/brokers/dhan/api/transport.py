"""DhanTransport — domain ports over the Dhan gateway facade (transport).

``DhanOrderTransport`` / ``DhanTransport`` wrap ``DhanWireAdapter`` so OMS and
Instrument code depend on ``ExecutionProvider`` / ``BrokerTransport``, not the
gateway class. The gateway remains as ops transport (Wave C — evolutionary).
"""

from __future__ import annotations

import contextlib
from typing import Any

from brokers.common.transport_errors import order_result_from_transport_error
from domain.capabilities import Capability
from domain.orders.requests import OrderRequest
from domain.ports.order_placement import OrderPlacementPort, invoke_place_order
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

    def __init__(self, gateway: OrderPlacementPort) -> None:
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
            response = invoke_place_order(self._gateway, request)
        except Exception as exc:  # transport boundary: never raise into domain
            return order_result_from_transport_error(exc)
        return self._wrap(response)

    def cancel_order(self, order_id: str) -> OrderResult:
        try:
            return self._wrap(self._gateway.cancel_order(order_id))
        except Exception as exc:
            return order_result_from_transport_error(exc)

    def modify_order(self, request) -> OrderResult:
        try:
            return self._wrap(
                self._gateway.modify_order(
                    request.order_id, price=request.price, quantity=request.quantity
                )
            )
        except Exception as exc:
            return order_result_from_transport_error(exc)

    def get_order_book(self):
        return self._gateway.get_orderbook()

    def get_positions(self):
        return self._gateway.positions()

    def get_holdings(self):
        return self._gateway.holdings()

    def get_funds(self):
        return self._gateway.funds()


class DhanTransport:
    """Concrete Dhan broker plugin — wraps gateway behind domain-shaped properties."""

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
        with contextlib.suppress(Exception):
            self._gateway.close()
