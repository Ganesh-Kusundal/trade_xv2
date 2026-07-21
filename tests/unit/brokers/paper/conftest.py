"""Shared test fixtures for brokers.providers.paper tests.

Provides PaperGateway fixtures, seeded mock brokers, and trading contexts
for deterministic testing without external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest

from brokers.providers.paper.paper_gateway import PaperGateway
from domain.entities import Order, Trade
from tests.e2e.fixtures.trading_context_factory import create_paper_trading_context


@dataclass
class _MockOrderResult:
    success: bool
    order: Order | None = None
    error: str | None = None


class MockPaperOrderManager:
    """Minimal OrderManager stand-in for paper unit tests."""

    def __init__(self) -> None:
        self._orders: list[Order] = []
        self._trades: list[Trade] = []
        self.risk_manager = None

    def place_order(self, *, request: Any, submit_fn: Any) -> _MockOrderResult:
        order = submit_fn(request)
        self._orders.append(order)
        return _MockOrderResult(success=True, order=order)

    def upsert_order(self, order: Order) -> None:
        self._orders.append(order)

    def record_trade(self, trade: Trade) -> bool:
        self._trades.append(trade)
        return True


@pytest.fixture
def mock_paper_order_manager() -> MockPaperOrderManager:
    return MockPaperOrderManager()


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def paper_gateway(mock_paper_order_manager):
    """Provide a PaperGateway instance with default capital."""
    return PaperGateway(
        initial_capital=Decimal("1000000"),
        order_manager=mock_paper_order_manager,
    )


@pytest.fixture
def paper_gateway_small_capital(mock_paper_order_manager):
    """Provide a PaperGateway with small capital for testing risk limits."""
    return PaperGateway(
        initial_capital=Decimal("10000"),
        order_manager=mock_paper_order_manager,
    )


@pytest.fixture
def seeded_paper_broker(mock_paper_order_manager):
    """Provide a PaperGateway pre-populated with realistic seed data."""
    return PaperGateway(
        initial_capital=Decimal("1000000"),
        order_manager=mock_paper_order_manager,
    )


@pytest.fixture
def paper_trading_context():
    """Provide a TradingContext configured for paper trading.

    Uses create_paper_trading_context() with permissive risk limits
    suitable for testing trading flows without restrictions.
    """
    return create_paper_trading_context(
        capital=Decimal("100000"),
        max_position_pct=Decimal("25"),
        max_gross_pct=Decimal("100"),
        max_daily_loss_pct=Decimal("5"),
    )


@pytest.fixture
def paper_trading_context_strict():
    """Provide a TradingContext with strict risk limits for testing rejections."""
    return create_paper_trading_context(
        capital=Decimal("100000"),
        max_position_pct=Decimal("5"),
        max_gross_pct=Decimal("50"),
        max_daily_loss_pct=Decimal("1"),
    )
