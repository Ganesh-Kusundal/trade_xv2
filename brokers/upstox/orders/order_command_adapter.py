"""Upstox order command adapter — implements ``OrderCommand`` port.

Mirrors ``brokers.dhan.orders.order_command_adapter.DhanOrderCommandAdapter``.
"""

from __future__ import annotations

import logging
from typing import Any

from brokers.common.api.ports import IdempotencyCachePort, OrderCommand
from brokers.common.core.models import (
    OrderPreview,
    OrderRequest,
    OrderResponse,
)
from brokers.upstox.instruments.resolver import UpstoxInstrumentResolver
from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
from brokers.upstox.orders.idempotency import InMemoryIdempotencyCache
from brokers.upstox.orders.order_client import UpstoxRestOrderClient

logger = logging.getLogger(__name__)


class UpstoxOrderCommandAdapter(OrderCommand):
    def __init__(
        self,
        order_client: UpstoxRestOrderClient,
        instrument_resolver: UpstoxInstrumentResolver,
        idempotency_cache: IdempotencyCachePort[OrderResponse] | None = None,
        *,
        use_v3: bool = True,
        algo_name: str | None = None,
        market_protection_default: int = -1,
    ) -> None:
        self._order_client = order_client
        self._instrument_resolver = instrument_resolver
        self._idempotency_cache = idempotency_cache or InMemoryIdempotencyCache()
        self._use_v3 = use_v3
        self._algo_name = algo_name
        self._market_protection_default = market_protection_default

    def place_order(self, request: OrderRequest) -> OrderResponse:
        if request.correlation_id and self._idempotency_cache is not None:
            cached = self._idempotency_cache.get(request.correlation_id)
            if cached is not None:
                return cached

        instrument_key = self._resolve_instrument_key(request)
        if not instrument_key:
            return OrderResponse.create_failure(
                f"Cannot resolve Upstox instrument_key for {request.symbol!r}"
            )

        preview = self.preview_order(request)
        if not preview.valid:
            return OrderResponse.create_failure("; ".join(preview.errors))

        payload = self._order_client.build_place_payload(
            request,
            instrument_key,
            algo_name=self._algo_name,
            market_protection=self._market_protection_default,
        )
        try:
            if self._use_v3:
                result = self._order_client.place_order_v3(payload)
            else:
                result = self._order_client.place_order_v2(payload)
        except Exception as exc:
            return OrderResponse.create_failure(str(exc))

        response = UpstoxDomainMapper.to_order_response(result)
        if request.correlation_id and self._idempotency_cache is not None and response.success:
            self._idempotency_cache.put(request.correlation_id, response)
        return response

    def modify_order(self, order_id: str, **changes: Any) -> dict[str, Any]:
        # Best-effort: caller must supply instrument_key in changes if needed.
        instrument_key = changes.pop("instrument_key", None) or order_id
        payload = UpstoxDomainMapper.to_modify_payload(order_id, instrument_key, **changes)
        return self._order_client.modify_order_v3(payload)

    def cancel_order(self, order_id: str) -> bool:
        try:
            result = self._order_client.cancel_order_v3(order_id)
            if isinstance(result, dict):
                if result.get("status") == "success":
                    return True
                data = result.get("data")
                if isinstance(data, dict) and data.get("order_id") == order_id:
                    return True
                if isinstance(data, list) and any(
                    isinstance(d, dict) and d.get("order_id") == order_id for d in data
                ):
                    return True
            return False
        except Exception:
            return False

    def preview_order(self, request: OrderRequest) -> OrderPreview:
        errors: list[str] = []
        if request.quantity <= 0:
            errors.append("quantity must be positive")
        if request.order_type.value in ("LIMIT", "SL") and (
            request.price is None or request.price <= 0
        ):
            errors.append("LIMIT/SL orders require price > 0")
        if request.order_type.value in ("SL", "SL-M") and (
            request.trigger_price is None or request.trigger_price <= 0
        ):
            errors.append("SL/SL-M orders require trigger_price > 0")
        return OrderPreview(valid=not errors, errors=errors)

    def _resolve_instrument_key(self, request: OrderRequest) -> str | None:
        # Prefer instrument_key if caller already set one
        if request.security_id and request.security_id != "":
            seg_wire = UpstoxDomainMapper.segment_to_wire(request.exchange_segment)
            return f"{seg_wire}|{request.security_id}"
        seg_wire = UpstoxDomainMapper.segment_to_wire(request.exchange_segment)
        definition = self._instrument_resolver.resolve(
            symbol=request.symbol, exchange_segment=seg_wire
        )
        if definition is not None:
            return definition.instrument_key
        # Last resort: assume symbol is the bare instrument_key
        return request.symbol or None
