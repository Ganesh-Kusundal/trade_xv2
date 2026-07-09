"""Unit tests for the Universe / Session public facade (composition root)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.entities.order import OrderResponse
from domain.instruments.instrument import Equity, Future, Index, Option
from domain.orders.requests import OrderRequest
from domain.ports.protocols import OrderResult
from domain.tests._fakes import FakeEventBus, FakeProvider
from domain.types import OrderType, Side
from domain.universe import Session, Universe


class FakeExecutionProvider:
    """Minimal ExecutionProvider for Session buy/sell unit tests."""

    name = "fake-exec"

    def __init__(self) -> None:
        self.requests: list[OrderRequest] = []

    def place_order(self, request: OrderRequest) -> OrderResult:
        self.requests.append(request)
        return OrderResult.ok(OrderResponse.ok(order_id=f"ORD-{len(self.requests)}"))

    def cancel_order(self, order_id: str) -> OrderResult:
        return OrderResult.ok(OrderResponse.ok(order_id=order_id))

    def modify_order(self, request) -> OrderResult:
        return OrderResult.ok(OrderResponse.ok(order_id=request.order_id))

    def get_order_book(self) -> list:
        return []

    def get_positions(self) -> list:
        return []

    def get_holdings(self) -> list:
        return []

    def get_funds(self):
        return None


def _new_session(
    *, with_exec: bool = False
) -> tuple[Session, FakeProvider, FakeEventBus, FakeExecutionProvider | None]:
    bus = FakeEventBus()
    fp = FakeProvider()
    fp.seed_quote("RELIANCE", "NSE", Decimal("2500"))
    executor = FakeExecutionProvider() if with_exec else None
    session = Session(fp, event_bus=bus, execution_provider=executor)
    return session, fp, bus, executor


def test_session_exposes_universe():
    session, _, _, _ = _new_session()
    assert isinstance(session.universe, Universe)
    assert session.provider.name == "fake"
    assert session.execution_provider is None


def test_universe_builds_equity():
    session, _, _, _ = _new_session()
    eq = session.universe.equity("RELIANCE")
    assert isinstance(eq, Equity)
    assert eq.symbol == "RELIANCE"
    assert eq.exchange == "NSE"


def test_universe_builds_index():
    session, _, _, _ = _new_session()
    idx = session.universe.index("NIFTY")
    assert isinstance(idx, Index)
    assert idx.symbol == "NIFTY"


def test_universe_builds_future():
    session, _, _, _ = _new_session()
    fut = session.universe.future("NIFTY", expiry=date(2026, 7, 31))
    assert isinstance(fut, Future)
    assert fut.expiry == date(2026, 7, 31)


def test_universe_builds_option():
    session, _, _, _ = _new_session()
    opt = session.universe.option(
        "RELIANCE", Decimal("2500"), "CE", expiry=date(2026, 7, 31)
    )
    assert isinstance(opt, Option)
    assert opt.strike == Decimal("2500")
    assert opt.is_call is True


def test_session_close_clears_default_provider():
    session, _, _, _ = _new_session()
    session.close()
    from domain.ports.provider_registry import get_default_provider

    assert get_default_provider() is None


def test_session_buy_requires_order_path():
    session, _, _, _ = _new_session(with_exec=False)
    eq = session.universe.equity("RELIANCE")
    with pytest.raises(RuntimeError, match="No order_service|execution_provider"):
        session.buy(eq, 10, price=Decimal("2500"))


def test_session_buy_via_execution_provider_legacy():
    """Legacy path: ExecutionProvider only (no OMS) still works for unit tests."""
    session, _, _, executor = _new_session(with_exec=True)
    assert executor is not None
    eq = session.universe.equity("RELIANCE")
    result = session.buy(eq, 10, price=Decimal("2500"))
    assert result.success is True
    assert len(executor.requests) == 1
    req = executor.requests[0]
    assert req.symbol == "RELIANCE"
    assert req.quantity == 10
    assert req.transaction_type == Side.BUY
    assert req.price == Decimal("2500")
    assert req.order_type == OrderType.LIMIT
    assert req.correlation_id  # intent always stamps correlation_id


def test_session_market_order():
    session, _, _, executor = _new_session(with_exec=True)
    assert executor is not None
    eq = session.universe.equity("RELIANCE")
    result = session.market(eq, 5, side="SELL")
    assert result.success is True
    req = executor.requests[0]
    assert req.transaction_type == Side.SELL
    assert req.order_type == OrderType.MARKET
    assert req.quantity == 5


def test_session_intent_builder():
    session, _, _, _ = _new_session(with_exec=True)
    eq = session.universe.equity("RELIANCE")
    intent = session.intent(eq, Side.BUY, 3, price=Decimal("100"))
    assert intent.symbol == "RELIANCE"
    assert intent.quantity == 3
    assert intent.correlation_id.startswith("intent:")


def test_session_place_via_order_service():
    """OrderServicePort is preferred over raw ExecutionProvider."""
    from domain.orders.intent import OrderIntent

    class CapturingOrderService:
        def __init__(self) -> None:
            self.intents: list[OrderIntent] = []

        def place(self, intent: OrderIntent) -> OrderResult:
            self.intents.append(intent)
            return OrderResult.ok(OrderResponse.ok(order_id="OMS-1"))

    bus = FakeEventBus()
    fp = FakeProvider()
    executor = FakeExecutionProvider()
    oms = CapturingOrderService()
    session = Session(fp, event_bus=bus, execution_provider=executor, order_service=oms)
    eq = session.universe.equity("RELIANCE")
    result = session.buy(eq, 2, price=Decimal("99"))
    assert result.success is True
    assert len(oms.intents) == 1
    assert oms.intents[0].quantity == 2
    assert executor.requests == []  # must not bypass OMS
