"""Quote resolution fail-closed for paper fills."""

from __future__ import annotations

from decimal import Decimal

import pytest

from application.oms.order_manager import OmsOrderCommand
from domain import OrderType, ProductType, Side
from domain.exceptions import QuoteUnavailableError


def test_quote_failure_rejects_order_not_zero_fill() -> None:
    from runtime.paper_session import build_paper_session

    def _fail_quote(symbol: str, exchange: str) -> Decimal:
        raise QuoteUnavailableError(f"no quote for {symbol}")

    session = build_paper_session(initial_capital=100_000, quote_fn=_fail_quote)
    cmd = OmsOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        price=Decimal("2500"),
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        correlation_id="quote-fail:1",
    )
    result = session.execution_engine.place_order(cmd)
    assert result.success is False
    assert result.order is not None
    assert result.order.filled_quantity == 0
    assert "no quote" in (result.error or "").lower()
