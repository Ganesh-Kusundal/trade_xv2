"""Bidirectional mappers between internal models (Pydantic) and canonical domain (dataclass).

Internal adapter layer uses ``models.py`` (Pydantic) for validation at boundaries.
External facade layer uses ``domain.py`` (dataclass) for consumer-facing APIs.
This module is the single translation point between the two.
"""

from __future__ import annotations

from decimal import Decimal

from brokers.common.core import domain, models
from brokers.common.core.enums import (
    ExchangeSegment,
    TransactionType,
)
from brokers.common.core.instruments import InstrumentRegistry


def _canonical_exchange(segment: ExchangeSegment) -> str:
    try:
        return InstrumentRegistry.canonical_exchange(segment)
    except KeyError:
        return segment.value if hasattr(segment, "value") else str(segment)


def _side_from_transaction(tx: TransactionType) -> domain.Side:
    return domain.Side.BUY if tx == TransactionType.BUY else domain.Side.SELL


# ── Order ──────────────────────────────────────────────────────────────────


def order_to_domain(m: models.Order) -> domain.Order:
    return domain.Order(
        order_id=m.order_id,
        symbol=m.symbol,
        exchange=_canonical_exchange(m.exchange_segment),
        side=_side_from_transaction(m.transaction_type),
        order_type=domain.OrderType(m.order_type.value),
        quantity=m.quantity,
        filled_quantity=m.filled_quantity,
        price=m.price,
        trigger_price=m.trigger_price if m.trigger_price is not None else Decimal("0"),
        status=domain.OrderStatus.normalize(m.status.value),
        timestamp=m.order_timestamp,
        product_type=domain.ProductType(m.product_type.value),
        validity=domain.Validity(m.validity.value),
        avg_price=m.average_price,
        reject_reason=m.reject_reason or "",
        correlation_id=m.correlation_id,
    )


def order_list_to_domain(items: list[models.Order]) -> list[domain.Order]:
    return [order_to_domain(m) for m in items]


# ── Position ───────────────────────────────────────────────────────────────


def position_to_domain(m: models.Position) -> domain.Position:
    return domain.Position(
        symbol=m.symbol,
        exchange=_canonical_exchange(m.exchange_segment),
        quantity=m.net_quantity if m.net_quantity else m.quantity,
        avg_price=m.buy_average_price if m.buy_average_price > 0 else Decimal("0"),
        ltp=m.last_price,
        unrealized_pnl=m.unrealized_pnl,
        realized_pnl=m.realized_pnl,
        product_type=domain.ProductType(m.product_type.value),
    )


def position_list_to_domain(items: list[models.Position]) -> list[domain.Position]:
    return [position_to_domain(m) for m in items]


# ── Holding ────────────────────────────────────────────────────────────────


def holding_to_domain(m: models.Holding) -> domain.Holding:
    return domain.Holding(
        symbol=m.symbol,
        exchange=_canonical_exchange(m.exchange_segment)
        if isinstance(m.exchange_segment, ExchangeSegment)
        else str(m.exchange_segment or "NSE"),
        quantity=m.quantity,
        available_quantity=m.available_quantity,
        avg_price=m.cost_price,
        ltp=m.last_price,
        pnl=m.pnl_value,
    )


def holding_list_to_domain(items: list[models.Holding]) -> list[domain.Holding]:
    return [holding_to_domain(m) for m in items]


# ── Trade ──────────────────────────────────────────────────────────────────


def trade_to_domain(m: models.Trade) -> domain.Trade:
    return domain.Trade(
        trade_id=m.trade_id,
        order_id=m.order_id,
        symbol=m.symbol,
        exchange=_canonical_exchange(m.exchange_segment)
        if isinstance(m.exchange_segment, ExchangeSegment)
        else str(m.exchange or "NSE"),
        side=_side_from_transaction(m.transaction_type),
        quantity=m.quantity,
        price=m.price,
        trade_value=m.trade_value if m.trade_value > 0 else m.price * Decimal(str(m.quantity)),
        timestamp=m.trade_timestamp,
        product_type=domain.ProductType(m.product_type.value),
    )


def trade_list_to_domain(items: list[models.Trade]) -> list[domain.Trade]:
    return [trade_to_domain(m) for m in items]


# ── FundLimits ─────────────────────────────────────────────────────────────


def fund_limits_to_domain(m: models.FundLimits) -> domain.FundLimits:
    return domain.FundLimits(
        available_balance=m.available_balance,
        used_margin=m.used_margin,
        total_margin=m.total_margin,
    )


# ── OrderResponse ──────────────────────────────────────────────────────────


def order_response_to_domain(m: models.OrderResponse) -> domain.OrderResponse:
    status = domain.OrderStatus.OPEN
    if m.order_status is not None:
        status = domain.OrderStatus.normalize(m.order_status.value)
    return domain.OrderResponse(
        success=m.success,
        order_id=m.order_id or "",
        message=m.message,
        status=status,
    )
