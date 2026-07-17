"""Tests for the CQRS CommandDispatcher / QueryDispatcher (ADR-012)."""

from __future__ import annotations

from decimal import Decimal

from domain.enums import OrderType, Side
from domain.events.types import DomainEvent, EventType
from application.oms.order_manager import OrderResult
from runtime.commands import (
    CommandDispatcher,
    CommandResult,
    LoadHistoryCommand,
    OrderCommandHandler,
    PlaceOrderCommand,
)
from runtime.queries import (
    CandleQuery,
    CandleQueryHandler,
    PortfolioQuery,
    PortfolioQueryHandler,
    QueryDispatcher,
    QueryResult,
)


class _FakeBus:
    """Minimal EventBusPort double that records published events."""

    def __init__(self) -> None:
        self.published: list[DomainEvent] = []

    def publish(self, event: DomainEvent) -> None:  # noqa: D401
        self.published.append(event)

    def subscribe(self, event_type: str, handler) -> None:  # noqa: D401
        pass


class _FakeOrderManager:
    """Records place_order calls; returns a fake order object."""

    def __init__(self) -> None:
        self.calls: list = []

    def place_order(self, request, submit_fn=None):
        self.calls.append((request, submit_fn))
        return OrderResult(
            success=True,
            order=_FakeOrder(order_id="O1", symbol=request.symbol),
        )


class _FakeOrder:
    def __init__(self, order_id="O1", symbol="RELIANCE") -> None:
        self.order_id = order_id
        self.symbol = symbol


class _FakePositionManager:
    def get_positions(self):
        return [{"symbol": "RELIANCE", "qty": 10}]


class _FakeQueryExecutor:
    def get_candles(self, symbol, timeframe="1m", lookback=300):
        return [{"symbol": symbol, "close": 100.0}]


def test_command_dispatcher_routes_to_handler() -> None:
    bus = _FakeBus()
    om = _FakeOrderManager()
    disp = CommandDispatcher(event_bus=bus)
    disp.register_handler(OrderCommandHandler(om))

    cmd = PlaceOrderCommand(
        correlation_id="c1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
    )
    result = disp.dispatch(cmd)

    assert result.success
    assert result.correlation_id == "c1"
    assert len(om.calls) == 1
    # Event published after success (async fan-out, decoupled from return).
    assert len(bus.published) == 1
    assert bus.published[0].event_type == EventType.ORDER_PLACED.value


def test_command_dispatcher_unknown_type_returns_error() -> None:
    disp = CommandDispatcher(event_bus=_FakeBus())
    cmd = PlaceOrderCommand(
        correlation_id="c2", symbol="X", exchange="NSE", side=Side.BUY, quantity=1
    )
    result = disp.dispatch(cmd)
    assert not result.success
    assert "No handler" in (result.error or "")


def test_command_dispatcher_no_event_on_failure() -> None:
    bus = _FakeBus()

    class _FailingHandler:
        handled_type = "place_order"

        def handle(self, command):
            return CommandResult(success=False, error="rejected", correlation_id=command.correlation_id)

    disp = CommandDispatcher(event_bus=bus)
    disp.register_handler(_FailingHandler())
    result = disp.dispatch(
        PlaceOrderCommand(correlation_id="c3", symbol="X", exchange="NSE", side=Side.BUY, quantity=1)
    )
    assert not result.success
    assert bus.published == []  # no event on failure


def test_query_dispatcher_is_read_only_and_returns_result() -> None:
    disp = QueryDispatcher()
    disp.register_handler(PortfolioQueryHandler(_FakePositionManager()))
    disp.register_handler(CandleQueryHandler(_FakeQueryExecutor()))

    p = disp.dispatch(PortfolioQuery(account_id="default"))
    assert p.success
    assert p.data == [{"symbol": "RELIANCE", "qty": 10}]

    c = disp.dispatch(CandleQuery(symbol="RELIANCE"))
    assert c.success
    assert c.data == [{"symbol": "RELIANCE", "close": 100.0}]


def test_query_dispatcher_unknown_type_returns_error() -> None:
    disp = QueryDispatcher()
    result = disp.dispatch(CandleQuery(symbol="X"))
    assert not result.success
    assert "No handler" in (result.error or "")


def test_order_command_handler_builds_oms_command() -> None:
    """Handler adapts PlaceOrderCommand into the canonical OmsOrderCommand."""
    om = _FakeOrderManager()
    handler = OrderCommandHandler(om)
    cmd = PlaceOrderCommand(
        correlation_id="c4",
        symbol="INFY",
        exchange="NSE",
        side=Side.SELL,
        quantity=5,
        price=Decimal("1500"),
        order_type=OrderType.LIMIT,
    )
    result = handler.handle(cmd)
    assert result.success
    sent_request, _ = om.calls[0]
    assert sent_request.symbol == "INFY"
    assert sent_request.side is Side.SELL
    assert sent_request.correlation_id == "c4"
