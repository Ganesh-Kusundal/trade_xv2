from __future__ import annotations

import logging
from typing import Any

from brokers.common.api.ports import IdempotencyCachePort, OrderCommand
from brokers.common.core.enums import OrderType  # F12 (M4): was missing
from brokers.common.core.models import OrderRequest, OrderResponse
from brokers.dhan.instrument_service import InstrumentService
from brokers.dhan.instruments.mixin import DhanInstrumentMixin
from brokers.dhan.orders.orders import DhanRestOrderClient
from brokers.dhan.orders.validator import DhanOrderValidator, OrderPreview

logger = logging.getLogger(__name__)


class DhanOrderCommandAdapter(DhanInstrumentMixin, OrderCommand):
    """Trade_J-style order command adapter over ``DhanRestOrderClient``."""

    def __init__(
        self,
        order_client: DhanRestOrderClient,
        instrument_service: Any | None = None,
        validator: DhanOrderValidator | None = None,
        idempotency_cache: IdempotencyCachePort[OrderResponse] | None = None,
    ) -> None:
        self._order_client = order_client
        if instrument_service is None:
            raise ValueError("DhanOrderCommandAdapter requires instrument_service")
        self._instrument_service = instrument_service
        self._validator = validator
        self._idempotency_cache = idempotency_cache

    @property
    def order_client(self) -> DhanRestOrderClient:
        return self._order_client

    @property
    def instrument_service(self) -> InstrumentService:
        return self._instrument_service

    @property
    def validator(self) -> DhanOrderValidator:
        return self._validator

    def place_order(self, request: OrderRequest) -> OrderResponse:
        if request.correlation_id and self._idempotency_cache:
            cached = self._idempotency_cache.get(request.correlation_id)
            if cached is not None:
                logger.info(
                    f"Returning cached order response for correlation_id: {request.correlation_id}"
                )
                return cached

        preview = self.preview_order(request)
        if not preview.valid:
            return OrderResponse.create_failure("; ".join(preview.errors))
        payload = self._payload_from_request(request)
        result = self._order_client.place_order_payload(payload)
        order_id = str(result.get("orderId") or result.get("data", {}).get("orderId") or "")
        if not order_id:
            response = OrderResponse.create_failure("Order placement did not return an orderId")
        else:
            response = OrderResponse.create_success(
                order_id,
                str(result),
            )

        if request.correlation_id and self._idempotency_cache:
            self._idempotency_cache.put(request.correlation_id, response)

        return response

    def modify_order(self, order_id: str, **changes: Any) -> dict[str, Any]:
        return self._order_client.modify_order(order_id, **changes)

    def cancel_order(self, order_id: str) -> bool:
        result = self._order_client.cancel_order(order_id)
        if isinstance(result, dict):
            return str(result.get("status", "")).lower() == "success"
        return False

    def preview_order(self, request: OrderRequest) -> OrderPreview:
        return self._validator.validate(request)

    def _payload_from_request(self, request: OrderRequest) -> dict[str, object]:
        security_id, wire_segment = self._resolve_and_segment(
            request.symbol,
            request.exchange,
        )
        payload: dict[str, object] = {
            "securityId": security_id,
            "exchangeSegment": wire_segment,
            "transactionType": request.transaction_type.value,
            "quantity": request.quantity,
            "orderType": request.order_type.value,
            "productType": request.product_type.value,
            "validity": request.validity.value,
        }
        if request.order_type == OrderType.LIMIT and request.price:
            payload["price"] = str(request.price)
        if request.trigger_price:
            payload["triggerPrice"] = str(request.trigger_price)
        if request.correlation_id:
            payload["correlationId"] = request.correlation_id
        if request.tag:
            payload["tag"] = request.tag
        return payload

    def subscribe_order_stream(self, order_ids: list[str]) -> bool:
        """Subscribe to order stream for specific order IDs."""
        return self._order_client.subscribe_order_stream(order_ids)

    def unsubscribe_order_stream(self, order_ids: list[str]) -> bool:
        """Unsubscribe from order stream for specific order IDs."""
        return self._order_client.unsubscribe_order_stream(order_ids)

    def get_order_stream_status(self) -> dict[str, Any]:
        """Get order stream status."""
        return self._order_client.get_order_stream_status()
