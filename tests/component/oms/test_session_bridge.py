"""Wave C: OrderIntent → Risk → OMS → ExecutionProvider spine."""

from __future__ import annotations

from decimal import Decimal

import pytest

from application.oms import register_oms_context, reset_oms_context
from application.oms.session_bridge import build_paper_oms_service, make_submit_fn
from domain.entities.order import OrderResponse
from domain.enums import OrderStatus, OrderType, ProductType, Side
from domain.orders.intent import OrderIntent
from domain.orders.requests import OrderRequest
from domain.ports.protocols import OrderResult
from tests.conftest import build_test_trading_context


class FakeExecutionProvider:
    name = "fake"

    def __init__(self) -> None:
        self.requests: list[OrderRequest] = []
        self.reject = False

    def place_order(self, request: OrderRequest) -> OrderResult:
        self.requests.append(request)
        if self.reject:
            return OrderResult.fail("broker down")
        return OrderResult.ok(
            OrderResponse.ok(order_id=f"BRK-{len(self.requests)}", status=OrderStatus.FILLED)
        )

    def cancel_order(self, order_id: str) -> OrderResult:
        return OrderResult.ok(OrderResponse.ok(order_id=order_id))

    def modify_order(self, request: OrderRequest) -> OrderResult:
        return OrderResult.ok(OrderResponse.ok(order_id="x"))

    def get_order_book(self) -> list:
        return []

    def get_positions(self) -> list:
        return []

    def get_holdings(self) -> list:
        return []

    def get_funds(self):
        return None


@pytest.fixture
def registered_paper_oms():
    """Wire process OMS context (composition-root path under test)."""
    reset_oms_context()
    ctx = build_test_trading_context(replay_events=False)
    register_oms_context(ctx)
    yield ctx
    reset_oms_context()


@pytest.fixture
def standalone_oms_wiring():
    """Infrastructure deps for explicit standalone build_oms_service tests."""
    from infrastructure.event_bus import EventBus
    from infrastructure.event_bus.processed_trade_repository import ProcessedTradeRepository

    return EventBus(), ProcessedTradeRepository()


def test_build_paper_oms_places_via_execution(registered_paper_oms):
    exec_p = FakeExecutionProvider()
    service = build_paper_oms_service(exec_p)
    intent = OrderIntent(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("2500"),
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        correlation_id="test:c1",
    )
    result = service.place(intent)
    assert result.success is True
    assert result.order is not None
    assert result.order.order_id == "BRK-1"
    assert result.order.correlation_id == "test:c1"
    assert len(exec_p.requests) == 1
    assert exec_p.requests[0].symbol == "RELIANCE"


def test_oms_idempotent_on_correlation_id(registered_paper_oms):
    exec_p = FakeExecutionProvider()
    service = build_paper_oms_service(exec_p)
    intent = OrderIntent(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        price=Decimal("100"),
        correlation_id="test:dup",
    )
    r1 = service.place(intent)
    r2 = service.place(intent)
    assert r1.success and r2.success
    assert r1.order.order_id == r2.order.order_id
    assert len(exec_p.requests) == 1  # second call must not re-submit


def test_risk_kill_switch_blocks_before_execution(registered_paper_oms):
    exec_p = FakeExecutionProvider()
    service = build_paper_oms_service(exec_p)
    service.order_manager.risk_manager.set_kill_switch(True)
    intent = OrderIntent(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        price=Decimal("100"),
        correlation_id="test:kill",
    )
    result = service.place(intent)
    assert result.success is False
    assert exec_p.requests == []


def test_execution_failure_surfaces_as_order_result(registered_paper_oms):
    exec_p = FakeExecutionProvider()
    exec_p.reject = True
    service = build_paper_oms_service(exec_p)
    intent = OrderIntent(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        price=Decimal("100"),
        correlation_id="test:fail",
    )
    result = service.place(intent)
    assert result.success is False
    assert "broker down" in (result.error or "")


def test_make_submit_fn_maps_order_response():
    exec_p = FakeExecutionProvider()
    submit = make_submit_fn(exec_p)
    from application.oms.order_manager import OmsOrderCommand

    cmd = OmsOrderCommand(
        symbol="TCS",
        exchange="NSE",
        side=Side.SELL,
        quantity=5,
        price=Decimal("3500"),
        correlation_id="test:map",
    )
    order = submit(cmd)
    assert order.order_id == "BRK-1"
    assert order.symbol == "TCS"
    assert order.side == Side.SELL
    assert order.status == OrderStatus.FILLED


def test_live_standalone_oms_refused_without_context():
    """ENG-001: live brokers must not get phantom-capital OMS by default."""
    from application.oms.session_bridge import build_oms_service

    reset_oms_context()
    exec_p = FakeExecutionProvider()
    try:
        build_oms_service(exec_p, broker_id="dhan")
        raise AssertionError("expected RuntimeError for live standalone OMS")
    except RuntimeError as exc:
        assert "ENG-001" in str(exc) or "phantom" in str(exc).lower() or "composition" in str(exc)


def test_live_standalone_allowed_with_explicit_flag(standalone_oms_wiring):
    from application.oms.session_bridge import build_oms_service

    event_bus, processed_trades = standalone_oms_wiring
    reset_oms_context()
    exec_p = FakeExecutionProvider()
    service = build_oms_service(
        exec_p,
        broker_id="upstox",
        allow_unsafe_standalone=True,
        capital=Decimal("50000"),
        event_bus=event_bus,
        processed_trade_repository=processed_trades,
    )
    intent = OrderIntent(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        price=Decimal("100"),
        correlation_id="test:unsafe-live",
    )
    result = service.place(intent)
    assert result.success is True


def test_paper_standalone_still_builds(standalone_oms_wiring):
    from application.oms.session_bridge import build_oms_service

    event_bus, processed_trades = standalone_oms_wiring
    reset_oms_context()
    exec_p = FakeExecutionProvider()
    service = build_oms_service(
        exec_p,
        broker_id="paper",
        event_bus=event_bus,
        processed_trade_repository=processed_trades,
    )
    assert service is not None


def test_unmapped_status_fails_closed():
    """ENG-005: unknown broker status must not become OPEN."""
    from application.oms.order_manager import OmsOrderCommand
    from application.oms.session_bridge import _execution_result_to_order
    from domain.ports.protocols import OrderResult

    class _Payload:
        order_id = "X1"
        status = "WEIRD_BROKER_STATE"

    cmd = OmsOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        price=Decimal("100"),
        correlation_id="test:status",
    )
    order = _execution_result_to_order(cmd, OrderResult.ok(_Payload()))
    assert order.status == OrderStatus.REJECTED
    assert "unmapped" in order.reject_reason.lower()
