"""Phase 2 architecture test: single OMS singleton per process.

Guards the money-path invariant: tradex.connect / Session.buy and the REST
API must resolve the SAME OrderManager + PositionManager. If they diverge,
fills land in a book the operator never queries (silent PnL desync).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from application.oms import (
    OrderManager,
    PositionManager,
    RiskConfig,
    RiskManager,
    TradingContext,
    get_oms_context,
    has_oms_context,
    register_oms_context,
    reset_oms_context,
)
from application.oms.session_bridge import build_paper_oms_service
from domain.enums import OrderStatus, OrderType, ProductType, Side
from domain.orders.intent import OrderIntent
from domain.ports.protocols import ExecutionProvider, OrderResult
from infrastructure.event_bus.event_bus import EventBus
from infrastructure.event_bus.processed_trade_repository import ProcessedTradeRepository


class _FakeExec(ExecutionProvider):
    name = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def place_order(self, request):  # type: ignore[override]
        self.calls += 1
        from domain.entities.order import OrderResponse

        return OrderResult.ok(
            OrderResponse.ok(order_id=f"BRK-{self.calls}", status=OrderStatus.FILLED)
        )

    def cancel_order(self, order_id):  # type: ignore[override]
        return OrderResult.ok("")

    def modify_order(self, request):  # type: ignore[override]
        return OrderResult.ok("")


@pytest.fixture
def fresh_oms():
    reset_oms_context()
    bus = EventBus()

    repo = ProcessedTradeRepository.get_instance(persistence_path=":memory:")
    ctx = TradingContext(
        event_bus=bus,
        order_manager=OrderManager(event_bus=bus, processed_trade_repository=repo),
        position_manager=PositionManager(event_bus=bus, processed_trade_repository=repo),
        risk_manager=RiskManager(PositionManager(), RiskConfig()),
        processed_trade_repository=repo,
    )
    register_oms_context(ctx)
    yield ctx
    reset_oms_context()


def test_tradex_connect_resolves_registered_singleton(fresh_oms: TradingContext) -> None:
    """tradex.connect's OMS service must be backed by the registered context."""
    import tradex

    exec_p = _FakeExec()
    # Build a session that shares the registered OMS by injecting its order_service.
    service = build_paper_oms_service(exec_p)
    # The build path resolves the singleton; both must point at the same manager.
    assert service.order_manager is fresh_oms.order_manager


def test_place_updates_same_book_queried_by_get_orders(fresh_oms: TradingContext) -> None:
    """A placed order is visible in the queried book (no silent desync)."""
    import tradex

    exec_p = _FakeExec()
    service = build_paper_oms_service(exec_p)
    intent = OrderIntent(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("2500"),
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        correlation_id="test:phase2",
    )
    result = service.place(intent)
    assert result.success
    # The same manager the API reads must hold the order.
    assert fresh_oms.order_manager.get_order(result.order.order_id) is not None


def test_only_one_registration_per_process(fresh_oms: TradingContext) -> None:
    other_bus = EventBus()
    other = TradingContext(
        event_bus=other_bus,
        order_manager=OrderManager(event_bus=other_bus),
        position_manager=PositionManager(event_bus=other_bus),
        risk_manager=RiskManager(PositionManager(), RiskConfig()),
        processed_trade_repository=ProcessedTradeRepository.get_instance(),
    )
    register_oms_context(other)  # second registration must be ignored
    assert get_oms_context() is fresh_oms
    assert has_oms_context()
