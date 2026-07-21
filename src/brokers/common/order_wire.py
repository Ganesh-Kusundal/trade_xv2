"""Map canonical OrderRequest to broker wire payloads at the transport boundary."""

from __future__ import annotations

from typing import Any

from domain.models.dtos import BrokerOrderPayload
from domain.orders.requests import OrderRequest
from domain.market_enums import ExchangeSegment


def order_request_to_payload(request: OrderRequest, broker_id: str) -> BrokerOrderPayload:
    """Build BrokerOrderPayload from OrderRequest using broker segment rules."""
    broker_id = (broker_id or "dhan").lower().strip()
    segment = _resolve_segment(request.exchange, broker_id)
    meta: dict[str, Any] = {}
    return BrokerOrderPayload(
        security_id="",
        symbol=request.symbol,
        exchange=request.exchange,
        transaction_type=request.transaction_type,
        quantity=request.quantity,
        price=request.price,
        trigger_price=request.trigger_price,
        order_type=request.order_type,
        product_type=request.product_type,
        validity=request.validity,
        correlation_id=request.correlation_id,
        tag=request.tag,
        slice=request.slice,
        disclosed_quantity=request.disclosed_quantity,
        slicing_algo=request.slicing_algo,
        slice_count=request.slice_count,
        slice_interval=request.slice_interval,
        twap_duration=request.twap_duration,
        vwap_participation_rate=request.vwap_participation_rate,
        exchange_segment=segment,
        provider_metadata=meta,
    )


def _resolve_segment(exchange: str, broker_id: str) -> ExchangeSegment:
    from domain.market.segment_mapper import segment_mapper_for

    return segment_mapper_for(broker_id).from_exchange(exchange)
