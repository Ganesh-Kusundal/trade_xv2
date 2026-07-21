"""Upstox order command adapter — implements ``OrderCommand`` port.

Mirrors ``brokers.dhan.orders.order_command_adapter.DhanOrderCommandAdapter``.
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Any

from brokers.common.idempotency import IdempotencyCache, IdempotencyCachePort
from brokers.common.order_validation import validate_tick_alignment
from brokers.common.transport_errors import order_response_from_transport_error
from brokers.upstox.instruments.resolver import UpstoxInstrumentResolver
from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
from brokers.upstox.orders.order_client import UpstoxRestOrderClient
from domain import (
    Order,
    OrderPreview,
    OrderRequest,
    OrderResponse,
)
from domain import Side as OrderSide
from domain.events import DomainEvent
from domain.models.dtos import BrokerOrderPayload
from domain.ports.risk_manager import RiskManagerPort
from infrastructure.event_bus.event_bus import EventBus

logger = logging.getLogger(__name__)


class UpstoxOrderCommandAdapter:
    def __init__(
        self,
        order_client: UpstoxRestOrderClient,
        instrument_resolver: UpstoxInstrumentResolver,
        idempotency_cache: IdempotencyCachePort[OrderResponse] | None = None,
        *,
        use_v3: bool = True,
        algo_name: str | None = None,
        market_protection_default: int = -1,
        event_bus: EventBus | None = None,
        risk_manager: RiskManagerPort | None = None,
    ) -> None:
        self._order_client = order_client
        self._instrument_resolver = instrument_resolver
        self._idempotency_cache = idempotency_cache or IdempotencyCache()
        self._use_v3 = use_v3
        self._algo_name = algo_name
        self._market_protection_default = market_protection_default
        self._event_bus = event_bus
        self._risk_manager = risk_manager

    def place_order(self, request: BrokerOrderPayload) -> OrderResponse:
        from domain.exceptions import OrderError

        cid = request.correlation_id
        if cid and self._idempotency_cache is not None:
            cached = self._idempotency_cache.get(cid)
            if cached is not None:
                return cached

            if not self._idempotency_cache.reserve(cid):
                logger.info("idempotency_waiting", extra={"correlation_id": cid})
                for _ in range(50):
                    cached = self._idempotency_cache.get(cid)
                    if cached is not None:
                        return cached
                    time.sleep(0.1)
                raise OrderError("concurrent placement for same correlation_id timed out")

        _post_sent = [False]
        try:
            response = self._place_order_impl(request, _post_sent)
        except Exception:
            # Only release the reservation when the POST was never sent.
            # If POST succeeded but response parsing raised, the order may
            # have been placed on the broker — clearing the reservation
            # would allow a retry to place a duplicate (P0.4 fix).
            if cid and self._idempotency_cache is not None and not _post_sent[0]:
                self._idempotency_cache.clear_reservation(cid)
            raise
        if cid and self._idempotency_cache is not None and not response.success:
            self._idempotency_cache.clear_reservation(cid)
        return response

    def _place_order_impl(
        self,
        request: BrokerOrderPayload,
        _post_sent: list[bool] | None = None,
    ) -> OrderResponse:
        from domain.exceptions import OrderError

        if self._risk_manager is not None:
            preview_order = self._to_domain_order(request)
            risk_result = self._risk_manager.check_order(preview_order)
            if not risk_result.allowed:
                return OrderResponse.fail(f"Risk check failed: {risk_result.reason}")

        instrument_key = self._resolve_instrument_key(request)

        preview = self.preview_order(request)
        if not preview.valid:
            raise OrderError("; ".join(preview.errors))

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
            return order_response_from_transport_error(exc)

        if _post_sent is not None:
            _post_sent[0] = True

        response = UpstoxDomainMapper.to_order_response(result)
        if response.success:
            if request.correlation_id and self._idempotency_cache is not None:
                self._idempotency_cache.commit(request.correlation_id, response)
            self._publish_order_placed(request, response)
        elif response.message:
            return OrderResponse.fail(response.message)
        return response

    def modify_order(self, order_id: str, **changes: Any) -> OrderResponse:
        """Modify an existing order via the Upstox V3 modify endpoint.

        The Upstox V3 modify API requires both ``order_id`` and
        ``instrument_token``.  If the caller does not supply
        ``instrument_key`` in ``changes``, we look up the existing order
        to resolve it automatically.
        """
        instrument_key = changes.pop("instrument_key", None)
        if not instrument_key:
            try:
                body = self._order_client.get_order(order_id)
                if isinstance(body, dict):
                    data = body.get("data")
                    if isinstance(data, list) and data:
                        instrument_key = data[0].get("instrument_token", "")
            except (ValueError, KeyError):
                logger.debug(
                    "Failed to look up order %s for instrument_key", order_id, exc_info=True
                )
        if not instrument_key:
            raise ValueError(
                f"Cannot modify order {order_id!r}: instrument_key is required but could "
                f"not be resolved (caller did not supply instrument_key and the order "
                f"lookup either failed or returned no instrument_token). Provide "
                f"instrument_key explicitly to modify_order."
            )
        payload = UpstoxDomainMapper.to_modify_payload(order_id, instrument_key, **changes)
        try:
            result = self._order_client.modify_order_v3(payload)
        except Exception as exc:
            return order_response_from_transport_error(exc)
        response = UpstoxDomainMapper.to_order_response(result)
        if not response.success:
            return response
        return OrderResponse.ok(
            order_id=order_id,
            message=response.message or "Order modified",
            status=response.status,
            raw_payload=result if isinstance(result, dict) else None,
        )

    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an order via the Upstox v3 cancel endpoint.

        Returns:
            :class:`OrderResponse` indicating success or carrying the
            broker's error code/message on failure.
        """
        from domain import OrderResponse

        try:
            result = self._order_client.cancel_order_v3(order_id)
        except Exception as exc:
            return order_response_from_transport_error(exc)
        if not isinstance(result, dict):
            return OrderResponse.fail(
                message="malformed broker response (not a dict)",
                raw_payload={"raw": repr(result)},
            )
        # Upstox v3 returns a top-level {"status":"success"} OR
        # {"data":{"order_id":...}}. Either indicates success.
        if str(result.get("status", "")).lower() in {"success", "ok"}:
            return OrderResponse.ok(
                order_id=order_id,
                message=str(result.get("message", "Order cancelled")),
                raw_payload=result,
            )
        data = result.get("data")
        if isinstance(data, dict) and data.get("order_id") == order_id:
            return OrderResponse.ok(
                order_id=order_id,
                message="Order cancelled",
                raw_payload=result,
            )
        if isinstance(data, list) and any(
            isinstance(d, dict) and d.get("order_id") == order_id for d in data
        ):
            return OrderResponse.ok(
                order_id=order_id,
                message="Order cancelled",
                raw_payload=result,
            )
        return OrderResponse.fail(
            message=str(
                result.get("errors", [{}])[0].get("message")
                if isinstance(result.get("errors"), list) and result.get("errors")
                else result.get("message", "Cancel failed")
            ),
            error_code=str(
                result.get("errors", [{}])[0].get("errorCode")
                if isinstance(result.get("errors"), list) and result.get("errors")
                else ""
            ),
            raw_payload=result,
        )

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

        # Tick size alignment (defense in depth)
        if request.price and request.price > 0:
            try:
                seg_wire = UpstoxDomainMapper.segment_to_wire(request.exchange)
                inst = self._instrument_resolver.resolve(
                    symbol=request.symbol, exchange_segment=seg_wire
                )
                if inst is not None:
                    tick_error = validate_tick_alignment(
                        request.price, Decimal(str(inst.tick_size)), request.symbol
                    )
                    if tick_error:
                        errors.append(tick_error)
            except Exception as exc:
                logger.debug("tick_check_skipped: %s", exc)

        return OrderPreview(valid=not errors, errors=errors)

    def _resolve_instrument_key(self, request: BrokerOrderPayload) -> str:
        from domain.exceptions import InstrumentNotFoundError

        seg_wire = UpstoxDomainMapper.segment_to_wire(request.exchange_segment)
        definition = self._instrument_resolver.resolve(
            symbol=request.symbol, exchange_segment=seg_wire
        )
        if definition is not None:
            return definition.instrument_key
        raise InstrumentNotFoundError(
            f"Cannot resolve Upstox instrument_key for {request.symbol!r} "
            f"on segment {request.exchange_segment!r}"
        )

    def _to_domain_order(self, request: BrokerOrderPayload) -> Order:
        from domain import OrderStatus, OrderType, ProductType, Validity
        from domain.ports.time_service import get_current_clock

        return Order(
            order_id="",
            symbol=request.symbol or "",
            exchange=request.exchange or "NSE",
            side=OrderSide(request.transaction_type.value),
            order_type=OrderType(request.order_type.value),
            quantity=request.quantity,
            price=request.price or Decimal("0"),
            trigger_price=request.trigger_price or Decimal("0"),
            product_type=ProductType(request.product_type.value),
            validity=Validity(request.validity.value),
            status=OrderStatus.OPEN,
            timestamp=get_current_clock().now(),
            correlation_id=request.correlation_id,
        )

    def _publish_order_placed(self, request: BrokerOrderPayload, response: OrderResponse) -> None:
        if self._event_bus is None:
            return
        from domain.ports.execution_context import is_oms_managed_submit

        if is_oms_managed_submit():
            return

        try:
            from dataclasses import replace

            order = replace(
                self._to_domain_order(request),
                order_id=response.order_id or "",
                status=response.status or self._to_domain_order(request).status,
            )
        except (RuntimeError, OSError):
            return
        self._event_bus.publish(
            DomainEvent.now(
                "ORDER_PLACED",
                {"order": order},
                symbol=order.symbol,
                source="UpstoxOrderCommandAdapter",
            )
        )
