"""Integration tests — paper OMS target boundary (ADR-0012)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from application.oms.order_manager import OmsOrderCommand
from domain import OrderType, ProductType, Side
from domain.ports.execution_target import ExecutionTargetKind
from runtime.execution_config import resolve_execution_target_kind
from runtime.paper_session import build_paper_session


def test_execution_target_defaults_to_paper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRADEX_EXECUTION_TARGET", raising=False)
    assert resolve_execution_target_kind() is ExecutionTargetKind.PAPER


def test_live_execution_target_rejected() -> None:
    with pytest.raises(RuntimeError, match="ADR-0013"):
        resolve_execution_target_kind(ExecutionTargetKind.LIVE)


def test_paper_session_uses_oms_capital_not_gateway() -> None:
    session = build_paper_session(initial_capital=50_000)
    balance = session.trading_context.risk_manager.capital_provider.get_available_balance()
    assert balance == Decimal("50000")


def test_paper_session_risk_and_context_share_position_manager() -> None:
    """R1: RiskManager must observe the same book as TradingContext (D-04)."""
    session = build_paper_session(initial_capital=100_000)
    ctx = session.trading_context
    assert ctx.risk_manager._position_manager is ctx.position_manager


def test_paper_fill_uses_quote_fn_price() -> None:
    prices = {"RELIANCE": Decimal("2500.50")}

    def quote_fn(symbol: str, exchange: str) -> Decimal:
        return prices.get(symbol, Decimal("0"))

    session = build_paper_session(initial_capital=100_000, quote_fn=quote_fn)
    cmd = OmsOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        price=Decimal("2500.50"),
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        correlation_id="paper:test:1",
    )
    result = session.execution_engine.place_order(cmd)
    assert result.success
    assert result.order is not None
    price = (
        result.order.price.to_decimal()
        if hasattr(result.order.price, "to_decimal")
        else Decimal(str(result.order.price))
    )
    assert price == Decimal("2500.50")
