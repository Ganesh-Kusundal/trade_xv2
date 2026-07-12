"""Normalize local OMS snapshots for ReconciliationEngine comparisons."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from domain import Order, OrderStatus, OrderType, Position, ProductType, Side, Validity


def _parse_status(raw: Any) -> OrderStatus:
    try:
        return OrderStatus(str(raw or OrderStatus.OPEN.value))
    except ValueError:
        return OrderStatus.OPEN


def local_orders_as_domain(items: list[Any] | None) -> list[Order] | None:
    if items is None:
        return None
    out: list[Order] = []
    for item in items:
        if isinstance(item, Order):
            out.append(item)
            continue
        if not isinstance(item, dict):
            continue
        out.append(
            Order(
                order_id=str(item.get("order_id", "")),
                symbol=str(item.get("symbol", "")),
                exchange=str(item.get("exchange", "NSE")),
                side=Side(str(item.get("side", Side.BUY.value))),
                order_type=OrderType(str(item.get("order_type", OrderType.MARKET.value))),
                quantity=int(item.get("quantity") or 0),
                filled_quantity=int(item.get("filled_quantity") or 0),
                price=Decimal(str(item.get("price") or 0)),
                avg_price=Decimal(str(item.get("avg_price") or 0)),
                product_type=ProductType(str(item.get("product_type", ProductType.INTRADAY.value))),
                validity=Validity.DAY,
                status=_parse_status(item.get("status")),
            )
        )
    return out


def local_positions_as_domain(items: list[Any] | None) -> list[Position] | None:
    if items is None:
        return None
    out: list[Position] = []
    for item in items:
        if isinstance(item, Position):
            out.append(item)
            continue
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or item.get("trading_symbol") or "")
        exchange = str(item.get("exchange") or item.get("exchange_segment") or "NSE")
        qty = int(item.get("quantity") or item.get("net_quantity") or 0)
        out.append(
            Position(
                symbol=symbol,
                exchange=exchange,
                quantity=qty,
                avg_price=Decimal(str(item.get("avg_price") or item.get("average_price") or 0)),
            )
        )
    return out