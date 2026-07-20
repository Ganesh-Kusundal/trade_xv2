"""Derivatives-specific Upstox domain mappers.

Extracted from ``domain_mapper.py`` (Task 2).  Contains methods for
historical candles, market depth, order responses, and order placement/
modification payloads — all shared across futures and options flows.
"""

from __future__ import annotations

import logging
from datetime import timezone
from decimal import Decimal
from typing import Any

from domain import (
    DepthLevel,
    MarketDepth,
    Order,
    OrderRequest,
    OrderResponse,
    OrderStatus,
    OrderType,
    Side,
    Validity,
)
from domain.candles.historical import HistoricalBar, InstrumentRef
from domain.ports.time_service import get_current_clock
from domain.provenance import DataProvenance
from domain.status_mapper import UnmappedBrokerStatusError

from ._base import (
    PROVIDER_ALGO_NAME,
    PROVIDER_IS_AMO,
    PROVIDER_MARKET_PROTECTION,
    order_type_from_wire,
    order_type_to_wire,
    parse_iso,
    product_from_wire,
    product_to_wire,
    str_or_none,
    to_int,
    txn_from_wire,
    txn_to_wire,
    validity_from_wire,
    validity_to_wire,
    wire_status_to_domain_status,
)
from .price_parser import UpstoxPriceParser

logger = logging.getLogger(__name__)


def to_place_payload(
    request: OrderRequest,
    instrument_key: str,
    *,
    algo_name: str | None = None,
    market_protection: int | None = None,
    slice_orders: bool = False,
) -> dict[str, Any]:
    provider_metadata = getattr(request, "provider_metadata", {}) or {}
    is_market = request.order_type == OrderType.MARKET
    from domain.value_objects.price import to_wire_float

    price_value = (
        0
        if is_market
        else (to_wire_float(request.price) if request.price and request.price > 0 else 0)
    )
    payload: dict[str, Any] = {
        "quantity": request.quantity,
        "product": product_to_wire(request.product_type),
        "validity": validity_to_wire(request.validity),
        "price": price_value,
        "instrument_token": instrument_key,
        "order_type": order_type_to_wire(request.order_type),
        "transaction_type": txn_to_wire(request.transaction_type),
        "disclosed_quantity": int(getattr(request, "disclosed_quantity", 0) or 0),
        "trigger_price": to_wire_float(request.trigger_price) if request.trigger_price else 0,
        PROVIDER_IS_AMO: bool(provider_metadata.get(PROVIDER_IS_AMO, False)),
    }
    tag = request.correlation_id or request.tag
    if tag:
        payload["tag"] = str(tag)[:40]
    if getattr(request, "slice", False) or slice_orders:
        payload["slice"] = True
    mp = market_protection
    if mp is None:
        mp = provider_metadata.get(PROVIDER_MARKET_PROTECTION, -1)
    payload[PROVIDER_MARKET_PROTECTION] = int(mp) if mp is not None else -1
    if algo_name:
        payload.setdefault(PROVIDER_ALGO_NAME, algo_name)
    return payload


def to_modify_payload(
    order_id: str,
    instrument_key: str,
    *,
    quantity: int | None = None,
    price: Decimal | None = None,
    trigger_price: Decimal | None = None,
    order_type: OrderType | None = None,
    validity: Validity | None = None,
    market_protection: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "order_id": order_id,
        "instrument_token": instrument_key,
    }
    if quantity is not None:
        payload["quantity"] = int(quantity)
    if price is not None:
        from domain.value_objects.price import to_wire_float

        payload["price"] = to_wire_float(price)
    if trigger_price is not None:
        from domain.value_objects.price import to_wire_float

        payload["trigger_price"] = to_wire_float(trigger_price)
    if order_type is not None:
        payload["order_type"] = order_type_to_wire(order_type)
    if validity is not None:
        payload["validity"] = validity_to_wire(validity)
    if market_protection is not None:
        payload["market_protection"] = int(market_protection)
    return payload


def to_order_response(payload: Any) -> OrderResponse:
    if not isinstance(payload, dict):
        return OrderResponse.fail("Order failed: unexpected response")
    errors = payload.get("errors")
    if errors:
        first = errors[0] if isinstance(errors, list) and errors else {}
        if isinstance(first, dict):
            message = first.get("message") or first.get("error") or str(first)
        else:
            message = str(first)
        return OrderResponse.fail(message)
    data = payload.get("data")
    if isinstance(data, dict):
        order_id = str(data.get("order_id") or payload.get("order_id") or "")
    else:
        order_id = str(payload.get("order_id") or "")
    if not order_id:
        remarks = payload.get("remarks") or payload.get("message") or "Order failed"
        return OrderResponse.fail(remarks)

    status_str = str(data.get("status") or payload.get("status") or "")
    try:
        status = wire_status_to_domain_status(status_str) if status_str else OrderStatus.OPEN
    except UnmappedBrokerStatusError as exc:
        # Re-bind logger locally so tests that patch logging.getLogger work
        _logger = logging.getLogger(__name__)
        _logger.error(
            "unmapped_order_status_in_response",
            extra={"order_id": order_id, "raw_status": status_str, "error": str(exc)},
        )
        status = OrderStatus.OPEN

    return OrderResponse.ok(
        order_id=order_id, message=str(data) if data is not None else "", status=status
    )


def to_historical_candle(
    payload: Any,
    *,
    symbol: str = "",
    exchange: str = "NSE",
    timeframe: str = "1D",
) -> HistoricalBar:
    if not isinstance(payload, dict):
        raise ValueError("expected dict candle payload")
    ts = parse_iso(payload.get("timestamp") or payload.get("time")) or get_current_clock().now()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return HistoricalBar(
        instrument=InstrumentRef(
            symbol=symbol or str(payload.get("symbol", "")), exchange=exchange
        ),
        timeframe=timeframe,
        event_time=ts,
        open=UpstoxPriceParser.parse(payload.get("open") or 0),
        high=UpstoxPriceParser.parse(payload.get("high") or 0),
        low=UpstoxPriceParser.parse(payload.get("low") or 0),
        close=UpstoxPriceParser.parse(payload.get("close") or 0),
        volume=to_int(payload.get("volume")),
        open_interest=to_int(payload.get("open_interest") or payload.get("oi")),
        provenance=DataProvenance.now(
            broker_id="upstox",
            request_id="wire.historical_candle",
            provider_timestamp=ts,
            transformation_chain=("upstox.historical.v1",),
        ),
    )


def to_historical_candles(
    payload: Any,
    *,
    symbol: str = "",
    exchange: str = "NSE",
    timeframe: str = "1D",
) -> list[HistoricalBar]:
    candles: list[HistoricalBar] = []
    if not isinstance(payload, dict):
        return candles
    data = payload.get("data") or payload
    if isinstance(data, dict):
        rows = data.get("candles") or data.get("data") or []
    else:
        rows = data or payload.get("candles") or []
    if not isinstance(rows, list):
        return candles
    for row in rows:
        if isinstance(row, list) and len(row) >= 5:
            ts = parse_iso(row[0]) or get_current_clock().now()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            candles.append(
                HistoricalBar(
                    instrument=InstrumentRef(symbol=symbol, exchange=exchange),
                    timeframe=timeframe,
                    event_time=ts,
                    open=UpstoxPriceParser.parse(row[1]),
                    high=UpstoxPriceParser.parse(row[2]),
                    low=UpstoxPriceParser.parse(row[3]),
                    close=UpstoxPriceParser.parse(row[4]),
                    volume=to_int(row[5]) if len(row) > 5 else 0,
                    provenance=DataProvenance.now(
                        broker_id="upstox",
                        request_id="wire.historical_candles",
                        provider_timestamp=ts,
                        transformation_chain=("upstox.historical.v1",),
                    ),
                )
            )
        elif isinstance(row, dict):
            candles.append(
                to_historical_candle(row, symbol=symbol, exchange=exchange, timeframe=timeframe)
            )
    return candles


def to_market_depth(payload: Any) -> MarketDepth:
    if not isinstance(payload, dict):
        return MarketDepth()
    data = payload.get("data") if "data" in payload else payload
    if not isinstance(data, dict):
        return MarketDepth()
    depth = data.get("depth")
    if depth is None:
        for _key, value in data.items():
            if isinstance(value, dict) and "depth" in value:
                depth = value.get("depth", {})
                break
    depth = depth or {}
    bids = depth.get("buy") or []
    asks = depth.get("sell") or []

    def _to_levels(rows):
        out = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            out.append(
                DepthLevel(
                    price=UpstoxPriceParser.parse(row.get("price") or 0),
                    quantity=to_int(row.get("quantity")),
                    orders=to_int(row.get("orders")),
                )
            )
        return out

    return MarketDepth(
        bids=_to_levels(bids),
        asks=_to_levels(asks),
    )


def to_order(payload: Any) -> Order:
    if not isinstance(payload, dict):
        return Order(
            order_id="",
            symbol="",
            exchange="",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=0,
        )
    return Order(
        order_id=str(payload.get("order_id") or ""),
        correlation_id=str_or_none(payload.get("tag")),
        symbol=str(payload.get("trading_symbol") or payload.get("symbol") or ""),
        exchange=str(payload.get("exchange") or ""),
        side=txn_from_wire(str(payload.get("transaction_type") or "BUY")),
        quantity=to_int(payload.get("quantity")),
        price=UpstoxPriceParser.parse(payload.get("price") or 0),
        trigger_price=UpstoxPriceParser.parse(payload.get("trigger_price") or 0),
        order_type=order_type_from_wire(str(payload.get("order_type") or "MARKET")),
        product_type=product_from_wire(str(payload.get("product") or "I")),
        validity=validity_from_wire(str(payload.get("validity") or "DAY")),
        status=wire_status_to_domain_status(str(payload.get("status") or "")),
        filled_quantity=to_int(payload.get("filled_quantity")),
        avg_price=UpstoxPriceParser.parse(payload.get("average_price") or 0),
        timestamp=parse_iso(payload.get("order_timestamp")),
        reject_reason=str_or_none(payload.get("status_message") or payload.get("rejection_reason"))
        or "",
    )
