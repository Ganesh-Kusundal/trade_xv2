"""Shared helpers for component UI tests using PaperGateway."""

from __future__ import annotations

from decimal import Decimal

from domain.enums import Side
from domain.orders.requests import OrderRequest


def paper_limit_order(
    symbol: str = "RELIANCE",
    exchange: str = "NSE",
    quantity: int = 10,
    *,
    price: Decimal = Decimal("2500"),
) -> OrderRequest:
    return OrderRequest(symbol, exchange, Side.BUY, quantity, price=price)
