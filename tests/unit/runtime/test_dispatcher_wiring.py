"""Tests for P2/P3: dispatcher wiring into Session + TradingOrchestrator (ADR-012)."""

from __future__ import annotations

from decimal import Decimal

from domain.enums import OrderType, Side
from domain.events.types import DomainEvent, EventType
from domain.models.trading import CandidateDTO, SignalDTO
from domain.universe import Session
from runtime.commands import (
    CommandDispatcher,
    HistoryCommandHandler,
    LoadHistoryCommand,
    OrderCommandHandler,
    PlaceOrderCommand,
    SubscribeCommandHandler,
    SubscribeInstrumentCommand,
)
from runtime.queries import PortfolioQuery, PortfolioQueryHandler, QueryDispatcher
from tests.conftest import build_test_trading_context


class _FakeBus:
    def __init__(self) -> None:
        self.published: list[DomainEvent] = []
        self.replay_mode = False
        self.logging_enabled = False

    def publish(self, event: DomainEvent) -> None:
        self.published.append(event)

    def subscribe(self, event_type: str, handler) -> None:
        pass

    def set_replay_mode(self, enabled: bool) -> None:
        self.replay_mode = enabled

    def set_logging_enabled(self, enabled: bool) -> None:
        self.logging_enabled = enabled


def _make_orchestrator(order_manager, bus):
    """Build a TradingOrchestrator with an injected order-command fn (P3)."""
    from application.trading.trading_orchestrator import (
        OrchestratorConfig,
        TradingOrchestrator,
    )
    from runtime.commands import CommandDispatcher, OrderCommandHandler, PlaceOrderCommand
    from application.oms.order_manager import OrderResult

    dispatcher = CommandDispatcher(event_bus=bus)
    dispatcher.register_handler(OrderCommandHandler(order_manager))

    def order_command_fn(oms_cmd):
        cmd = PlaceOrderCommand(
            correlation_id=oms_cmd.correlation_id,
            symbol=oms_cmd.symbol,
            exchange=oms_cmd.exchange,
            side=oms_cmd.side,
            quantity=oms_cmd.quantity,
            price=oms_cmd.price,
            order_type=oms_cmd.order_type,
            product_type=oms_cmd.product_type,
        )
        result = dispatcher.dispatch(cmd)
        return OrderResult(
            success=result.success, order=result.data, error=result.error or ""
        )

    orch = TradingOrchestrator(
        event_bus=bus,
        order_manager=order_manager,
        strategy_evaluator=_FakeStrategy(),
        feature_fetcher=_FakeFetcher(),
        config=OrchestratorConfig(dry_run=False, min_confidence=0.0),
        order_command_fn=order_command_fn,
    )
    return orch


class _FakeStrategy:
    def evaluate_single(self, candidate, features):
        return [
            SignalDTO(
                symbol=candidate.symbol,
                exchange=candidate.exchange,
                side="BUY",
                signal_type="BUY",
                confidence=Decimal("0.9"),
                entry_price=Decimal("100"),
            )
        ]


class _FakeFetcher:
    def fetch(self, symbol):
        return None

    def __call__(self, symbol):
        return self.fetch(symbol)


def test_orchestrator_routes_signal_through_command_dispatcher() -> None:
    """P3: a signal must flow through the CommandDispatcher, not call OMS directly."""
    bus = _FakeBus()
    ctx = build_test_trading_context(event_bus=bus)
    om = ctx.order_manager

    orch = _make_orchestrator(om, bus)

    signal = SignalDTO(
        symbol="RELIANCE",
        exchange="NSE",
        side="BUY",
        signal_type="BUY",
        confidence=Decimal("0.9"),
        entry_price=Decimal("100"),
    )
    orch._execute_signal(signal, correlation_id="cid-1")

    # Order placed via dispatcher -> OMS -> ORDER_PLACED event published.
    assert any(e.event_type == EventType.ORDER_PLACED.value for e in bus.published)
    assert len(om.get_orders(symbol="RELIANCE")) >= 1


def test_session_exposes_dispatchers_and_routes_order() -> None:
    """P2: DomainSession exposes a CommandDispatcher that routes an order."""
    bus = _FakeBus()
    ctx = build_test_trading_context(event_bus=bus)
    om = ctx.order_manager

    dispatcher = CommandDispatcher(event_bus=bus)
    dispatcher.register_handler(OrderCommandHandler(om))

    query_dispatcher = QueryDispatcher()
    query_dispatcher.register_handler(PortfolioQueryHandler(ctx.position_manager))

    session = Session(_ProviderStub(), event_bus=bus)
    session.attach_command_dispatcher(dispatcher)
    session.attach_query_dispatcher(query_dispatcher)

    assert session.command_dispatcher is dispatcher
    assert session.query_dispatcher is query_dispatcher

    from runtime.commands import PlaceOrderCommand

    result = session.command_dispatcher.dispatch(
        PlaceOrderCommand(
            correlation_id="cid-2",
            symbol="INFY",
            exchange="NSE",
            side=Side.BUY,
            quantity=5,
        )
    )
    assert result.success
    assert any(e.event_type == EventType.ORDER_PLACED.value for e in bus.published)

    # Query path is read-only and returns positions.
    q = session.query_dispatcher.dispatch(PortfolioQuery())
    assert q.success


def test_session_place_routes_through_command_dispatcher() -> None:
    """P2/P4: Session.place() uses the injected order-command closure."""
    bus = _FakeBus()
    ctx = build_test_trading_context(event_bus=bus)
    om = ctx.order_manager

    dispatcher = CommandDispatcher(event_bus=bus)
    dispatcher.register_handler(OrderCommandHandler(om))

    session = Session(_ProviderStub(), event_bus=bus)
    session.attach_command_dispatcher(dispatcher)

    # Build the same closure the composition root builds (ADR-012).
    from domain.ports import OrderResult as PortOrderResult
    from runtime.commands import PlaceOrderCommand

    def order_command_fn(intent):
        cmd = PlaceOrderCommand(
            correlation_id=intent.correlation_id,
            symbol=intent.symbol,
            exchange=intent.exchange,
            side=intent.side,
            quantity=intent.quantity,
            price=intent.price,
            order_type=intent.order_type,
            product_type=intent.product_type,
        )
        result = dispatcher.dispatch(cmd)
        return PortOrderResult(
            success=result.success, order=result.data, error=result.error or ""
        )

    session.attach_order_command_fn(order_command_fn)

    from domain.orders.intent import OrderIntent
    from domain.enums import Side

    intent = OrderIntent(
        symbol="RELIANCE", exchange="NSE", side=Side.BUY, quantity=10
    )
    result = session.place(intent)
    assert result.success
    assert any(e.event_type == EventType.ORDER_PLACED.value for e in bus.published)


def test_subscribe_and_history_handlers_use_data_provider() -> None:
    """P4: subscribe/history commands route through the session DataProvider."""
    bus = _FakeBus()
    provider = _FakeDataProvider()
    dispatcher = CommandDispatcher(event_bus=bus)
    dispatcher.register_handler(SubscribeCommandHandler(provider))
    dispatcher.register_handler(HistoryCommandHandler(provider))

    sub = dispatcher.dispatch(
        SubscribeInstrumentCommand(correlation_id="s1", instrument_id="RELIANCE:NSE")
    )
    assert sub.success
    assert provider.subscribed == ["RELIANCE:NSE"]

    hist = dispatcher.dispatch(
        LoadHistoryCommand(correlation_id="h1", symbol="RELIANCE:NSE", timeframe="1m")
    )
    assert hist.success
    assert hist.data == [{"symbol": "RELIANCE:NSE", "close": 100.0}]


class _FakeDataProvider:
    def __init__(self) -> None:
        self.subscribed: list[str] = []

    def subscribe(self, instrument_id, callback=None, *, depth=False):
        self.subscribed.append(instrument_id)
        return f"handle:{instrument_id}"

    def history_batch(self, instrument_ids, *, timeframe="1D", lookback_days=120):
        return [{"symbol": instrument_ids[0], "close": 100.0}]


class _ProviderStub:
    name = "stub"
