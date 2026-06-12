"""REST order client — place, modify, cancel order management operations.

Design reference: Trade_J ``DhanRestOrderClient``.

All mutating calls are wrapped through :class:`~broker.resilience.retry.RetryExecutor`
supplied at construction time, providing automatic circuit-breaker and rate-limit
integration.
"""

from __future__ import annotations

from typing import Any

from brokers.common.core.models import ModifyOrderRequest, OrderRequest
from brokers.common.resilience.retry import RetryExecutor
from brokers.dhan.instrument_service import InstrumentService
from brokers.dhan.mapper.instruments import DhanInstrumentDefinition
from brokers.dhan.mapper.mapping import list_data


class DhanRestOrderClient:
    """REST client for order/trade endpoints, matching Trade_J's DhanRestOrderClient."""

    def __init__(
        self,
        http_client: Any,
        settings: Any,
        url_resolver: Any,
        instrument_service: InstrumentService,
        retry_executor: RetryExecutor | None = None,
    ) -> None:
        self._http_client = http_client
        self._settings = settings
        self._url_resolver = url_resolver
        self._retry_executor = retry_executor
        self._instrument_service = instrument_service

    # ── Order lifecycle ─────────────────────────────────────────────

    def place_order(
        self,
        request: OrderRequest,
        definition: DhanInstrumentDefinition | None = None,
    ) -> dict[str, Any]:
        return self.place_order_payload(self._base_order_payload(request, definition))

    def place_order_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._retry_executor.execute(
            lambda: self._http_client.post_json(self._url_resolver.orders_url(), payload)
        )

    def modify_order(self, order_id: str, **changes: Any) -> dict[str, Any]:
        payload = {k: v for k, v in changes.items() if v is not None}
        return self._retry_executor.execute(
            lambda: self._http_client.put_json(self._url_resolver.order_url(order_id), payload)
        )

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return self._retry_executor.execute(
            lambda: self._http_client.delete_json(self._url_resolver.order_url(order_id))
        )

    def cancel_all_open_orders(self) -> list[str]:
        response = self._retry_executor.execute(
            lambda: self._http_client.delete_json(self._url_resolver.orders_url())
        )
        data = response.get("data", []) if isinstance(response, dict) else []
        return (
            [str(item.get("orderId") or item.get("id") or item) for item in data]
            if isinstance(data, list)
            else []
        )

    def place_slice_order(self, request: OrderRequest) -> list[dict[str, Any]]:
        payload = self._base_order_payload(request)
        response = self._retry_executor.execute(
            lambda: self._http_client.post_json(self._url_resolver.slice_order_url(), payload)
        )
        data = response.get("data") if isinstance(response, dict) else response
        return data if isinstance(data, list) else [response]

    def place_super_order(
        self,
        request: OrderRequest,
        target_price: float,
        stop_loss_price: float,
        trailing_jump: float,
    ) -> dict[str, Any]:
        payload = self._base_order_payload(request)
        payload.update(
            {
                "boProfitValue": float(target_price),
                "boStopLossValue": float(stop_loss_price),
                "trailingJump": float(trailing_jump),
            }
        )
        return self._retry_executor.execute(
            lambda: self._http_client.post_json(self._url_resolver.super_order_url(), payload)
        )

    def get_super_orders(self) -> list[dict[str, Any]]:
        response = self._retry_executor.execute(
            lambda: self._http_client.get_json(self._url_resolver.super_orders_url())
        )
        data = response.get("data") if isinstance(response, dict) else response
        return data if isinstance(data, list) else []

    def modify_super_order(
        self,
        order_id: str,
        leg_name: str,
        quantity: int,
        price: float,
        trigger_price: float,
    ) -> dict[str, Any]:
        payload = {
            "dhanClientId": self._settings.client_id,
            "orderId": order_id,
            "legName": leg_name,
            "quantity": quantity,
            "price": float(price),
            "triggerPrice": float(trigger_price),
        }
        return self._retry_executor.execute(
            lambda: self._http_client.put_json(
                self._url_resolver.super_order_leg_url(order_id, leg_name), payload
            )
        )

    def cancel_super_order(self, order_id: str, leg_name: str) -> bool:
        response = self._retry_executor.execute(
            lambda: self._http_client.delete_json(
                self._url_resolver.super_order_leg_url(order_id, leg_name)
            )
        )
        return "data" in response

    def place_forever_order(
        self,
        request: OrderRequest,
        order_flag: str,
        quantity2: int | None = None,
        price2: float | None = None,
        trigger_price2: float | None = None,
    ) -> dict[str, Any]:
        payload = self._base_order_payload(request)
        payload["orderFlag"] = order_flag
        if quantity2 is not None:
            payload["quantity2"] = quantity2
        if price2 is not None:
            payload["price2"] = float(price2)
        if trigger_price2 is not None:
            payload["triggerPrice2"] = float(trigger_price2)
        return self._retry_executor.execute(
            lambda: self._http_client.post_json(self._url_resolver.forever_orders_url(), payload)
        )

    def modify_forever_order(
        self,
        order_id: str,
        order_flag: str,
        leg_name: str,
        quantity: int,
        price: float,
        trigger_price: float,
    ) -> dict[str, Any]:
        payload = {
            "dhanClientId": self._settings.client_id,
            "orderId": order_id,
            "orderFlag": order_flag,
            "orderType": "LIMIT",
            "legName": leg_name,
            "quantity": quantity,
            "price": float(price),
            "triggerPrice": float(trigger_price),
            "validity": "DAY",
        }
        return self._retry_executor.execute(
            lambda: self._http_client.put_json(
                self._url_resolver.forever_order_url(order_id), payload
            )
        )

    def cancel_forever_order(self, order_id: str) -> bool:
        response = self._retry_executor.execute(
            lambda: self._http_client.delete_json(self._url_resolver.forever_order_url(order_id))
        )
        status = str(response.get("orderStatus") or response.get("status") or "")
        return not status or status.upper() == "CANCELLED"

    def get_forever_orders(self) -> list[dict[str, Any]]:
        response = self._retry_executor.execute(
            lambda: self._http_client.get_json(self._url_resolver.forever_orders_all_url())
        )
        data = response.get("data") if isinstance(response, dict) else response
        return data if isinstance(data, list) else []

    def modify_order_request(self, request: ModifyOrderRequest) -> dict[str, Any]:
        return self.modify_order(request.order_id, **request.to_changes())

    # ── Advanced Orders ─────────────────────────────────────────────

    def place_bracket_order(
        self,
        request: OrderRequest,
        profit_target: float,
        stop_loss: float,
        trailing_jump: float | None = None,
    ) -> dict[str, Any]:
        """Place a bracket order with profit target and stop loss."""
        payload = self._base_order_payload(request)
        payload.update(
            {
                "boProfitValue": float(profit_target),
                "boStopLossValue": float(stop_loss),
                "trailingJump": float(trailing_jump) if trailing_jump else 0.0,
            }
        )
        return self._retry_executor.execute(
            lambda: self._http_client.post_json(self._url_resolver.super_order_url(), payload)
        )

    def place_slice_order(
        self,
        request: OrderRequest,
        slice_quantity: int | None = None,
        slice_count: int | None = None,
    ) -> list[dict[str, Any]]:
        """Place a slice order with specified slice parameters."""
        payload = self._base_order_payload(request)
        if slice_quantity is not None:
            payload["sliceQuantity"] = slice_quantity
        if slice_count is not None:
            payload["sliceCount"] = slice_count

        response = self._retry_executor.execute(
            lambda: self._http_client.post_json(self._url_resolver.slice_order_url(), payload)
        )
        data = response.get("data") if isinstance(response, dict) else response
        return data if isinstance(data, list) else [response]

    def place_gtt_order(
        self,
        request: OrderRequest,
        comparison_type: str,
        operator: str,
        comparing_value: float,
        time_frame: str | None = None,
        expiry_date: str | None = None,
        user_note: str | None = None,
    ) -> dict[str, Any]:
        """Place a Good Till Trigger (GTT) order."""
        payload = self._base_order_payload(request)
        payload.update(
            {
                "comparisonType": comparison_type,
                "operator": operator,
                "comparingValue": float(comparing_value),
                "timeFrame": time_frame,
                "expiryDate": expiry_date,
                "userNote": user_note,
            }
        )
        return self._retry_executor.execute(
            lambda: self._http_client.post_json(self._url_resolver.gtt_order_url(), payload)
        )

    # ── Order queries ───────────────────────────────────────────────

    def get_orders(self) -> list[dict[str, Any]]:
        response = self._retry_executor.execute(
            lambda: self._http_client.get_json(self._url_resolver.orders_url())
        )
        return list_data(response)

    def get_order(self, order_id: str) -> dict[str, Any]:
        return self._retry_executor.execute(
            lambda: self._http_client.get_json(self._url_resolver.order_url(order_id))
        )

    def get_order_by_correlation_id(self, correlation_id: str) -> dict[str, Any]:
        return self._retry_executor.execute(
            lambda: self._http_client.get_json(
                self._url_resolver.order_by_correlation_id_url(correlation_id)
            )
        )

    def get_trades(self) -> list[dict[str, Any]]:
        response = self._retry_executor.execute(
            lambda: self._http_client.get_json(self._url_resolver.trades_url())
        )
        return list_data(response)

    def get_trades_for_order(self, order_id: str) -> list[dict[str, Any]]:
        response = self._retry_executor.execute(
            lambda: self._http_client.get_json(
                self._url_resolver.trades_url_for_order(order_id),
            ),
        )
        return list_data(response)

    # ── Kill switch ─────────────────────────────────────────────────

    def get_kill_switch_status(self) -> str:
        response = self._retry_executor.execute(
            lambda: self._http_client.get_json(self._url_resolver.kill_switch_url())
        )
        return str(response.get("killSwitchStatus") or response.get("status") or "")

    def set_kill_switch(self, enabled: bool) -> bool:
        response = self._retry_executor.execute(
            lambda: self._http_client.put_json(
                self._url_resolver.orders_url(),
                {
                    "killSwitch": "ACTIVATE" if enabled else "DEACTIVATE",
                },
            )
        )
        return "data" in response

    # ── Private helpers ─────────────────────────────────────────────

    def _base_order_payload(
        self,
        request: OrderRequest,
        definition: DhanInstrumentDefinition | None = None,
    ) -> dict[str, Any]:
        if definition is None:
            definition = self._resolve_definition(request)
        payload: dict[str, Any] = {
            "dhanClientId": self._settings.client_id,
            "securityId": definition.security_id,
            "exchangeSegment": definition.exchange_segment.value,
            "transactionType": request.transaction_type.value,
            "orderType": request.order_type.value,
            "productType": request.product_type.value,
            "validity": request.validity.value,
            "quantity": request.quantity,
        }
        if request.price > 0:
            payload["price"] = float(request.price)
        if request.trigger_price:
            payload["triggerPrice"] = float(request.trigger_price)
        if request.correlation_id:
            payload["correlationId"] = request.correlation_id
        return payload

    def _resolve_definition(self, request: OrderRequest) -> DhanInstrumentDefinition:
        defn = self._instrument_service.get_definition(
            security_id=request.security_id,
            segment=request.exchange_segment,
        )
        if defn is None:
            raise ValueError(
                f"No instrument found: security_id={request.security_id!r}, "
                f"segment={request.exchange_segment!r}"
            )
        return defn

    # ── Order stream ───────────────────────────────────────────────────

    def subscribe_order_stream(self, order_ids: list[str]) -> bool:
        """Subscribe to order stream for specific order IDs."""
        return self._retry_executor.execute(
            lambda: self._http_client.post_json(
                self._url_resolver.order_stream_url(), {"orderIds": order_ids}
            )
        )

    def unsubscribe_order_stream(self, order_ids: list[str]) -> bool:
        """Unsubscribe from order stream for specific order IDs."""
        return self._retry_executor.execute(
            lambda: self._http_client.delete_json(
                self._url_resolver.order_stream_url(), {"orderIds": order_ids}
            )
        )

    def get_order_stream_status(self) -> dict[str, Any]:
        """Get order stream status."""
        return self._retry_executor.execute(
            lambda: self._http_client.get_json(self._url_resolver.order_stream_status_url())
        )
