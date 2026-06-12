"""Dhan conditional alert adapter."""

from __future__ import annotations

from typing import Any

from brokers.common.api.ports import ConditionalAlertProvider
from brokers.common.core.models import ConditionalAlert, ConditionalAlertRequest
from brokers.common.resilience.retry import RetryExecutor
from brokers.dhan.auth.http import DhanAuthenticatedHttpClient
from brokers.dhan.auth.urls import DhanApiUrlResolver
from brokers.dhan.instrument_service import InstrumentService
from brokers.dhan.mapper.dhan_segment_mapper import to_wire_value
from brokers.dhan.mapper.mapping import str_field


class DhanConditionalAlertProvider(ConditionalAlertProvider):
    """Dhan conditional alert adapter."""

    def __init__(
        self,
        http_client: DhanAuthenticatedHttpClient,
        url_resolver: DhanApiUrlResolver,
        instrument_service: InstrumentService,
        retry_executor: Optional[RetryExecutor] = None,
    ) -> None:
        self._http_client = http_client
        self._url_resolver = url_resolver
        self._retry_executor = retry_executor
        self._instrument_service = instrument_service

    def place_alert(self, request: ConditionalAlertRequest) -> str:
        definition = self._instrument_service.get_definition(
            security_id=request.security_id,
            segment=request.exchange_segment,
        )
        if definition is None:
            raise ValueError(
                f"No instrument found: security_id={request.security_id!r}, "
                f"segment={request.exchange_segment!r}"
            )
        payload: dict[str, Any] = {
            "securityId": definition.security_id,
            "exchangeSegment": to_wire_value(definition.exchange_segment),
            "transactionType": request.transaction_type.value,
            "orderType": request.order_type.value,
            "productType": request.product_type.value,
            "quantity": request.quantity,
            "price": float(request.price),
            "triggerPrice": float(request.trigger_price),
            "validity": request.validity.value,
            "comparisonType": request.comparison_type,
        }
        self._optional(payload, "operator", request.operator)
        self._optional(payload, "timeFrame", request.time_frame)
        self._optional_decimal(payload, "comparingValue", request.comparing_value)
        self._optional(payload, "indicatorName", request.indicator_name)
        self._optional(payload, "comparingIndicatorName", request.comparing_indicator_name)
        self._optional(payload, "frequency", request.frequency)
        self._optional(payload, "expDate", request.expiry_date)
        self._optional(payload, "userNote", request.user_note)
        response = self._retry_executor.execute(
            lambda: self._http_client.post_json(self._url_resolver.alert_orders_url(), payload)
        )
        data = response.get("data") if isinstance(response, dict) else response
        if not isinstance(data, dict):
            data = response if isinstance(response, dict) else {}
        alert_id = str_field(data, "alertId", "id")
        return alert_id or str_field(data, "message")

    def get_alert(self, alert_id: str) -> ConditionalAlert:
        response = self._retry_executor.execute(
            lambda: self._http_client.get_json(self._url_resolver.alert_order_url(alert_id))
        )
        data = response.get("data") if isinstance(response, dict) else response
        if not isinstance(data, dict):
            data = response if isinstance(response, dict) else {}
        return self._alert(data)

    def list_alerts(self) -> list[ConditionalAlert]:
        response = self._retry_executor.execute(
            lambda: self._http_client.get_json(self._url_resolver.alert_orders_url())
        )
        data = response.get("data") if isinstance(response, dict) else response
        if not isinstance(data, list):
            return []
        return [self._alert(item) for item in data if isinstance(item, dict)]

    def delete_alert(self, alert_id: str) -> bool:
        self._retry_executor.execute(
            lambda: self._http_client.delete_json(self._url_resolver.alert_order_url(alert_id))
        )
        return True

    @staticmethod
    def _alert(data: dict[str, Any]) -> ConditionalAlert:
        return ConditionalAlert(
            alert_id=str_field(data, "alertId", "id"),
            status=str_field(data, "alertStatus", "status"),
            message=str_field(data, "message", "remarks"),
        )

    @staticmethod
    def _optional(payload: dict[str, Any], key: str, value: Any) -> None:
        if value:
            payload[key] = value

    @staticmethod
    def _optional_decimal(payload: dict[str, Any], key: str, value: Any) -> None:
        if value is not None:
            payload[key] = float(value)
