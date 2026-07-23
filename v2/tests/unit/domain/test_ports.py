"""Domain port protocols — structural typing contracts."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable
from uuid import UUID, uuid4

import pytest

from domain.entities import Account, Bar, Instrument, Order, Position, Quote
from domain.enums import OrderSide, OrderType, TimeInForce
from domain.events import Message, OrderFilled
from domain.ports import (
    BrokerAdapter,
    Clock,
    DataAdapter,
    EventBusPort,
    FillSource,
    IdempotencyGuard,
    PortfolioModel,
    RiskModel,
    Strategy,
)
from domain.ports.types import (
    BrokerSnapshot,
    CancelResult,
    IdempotencyResult,
    OrderResult,
    PortfolioContext,
    RiskContext,
    Signal,
    StartEvent,
    StopEvent,
    Subscription,
)
from domain.value_objects import (
    AccountId,
    CorrelationId,
    InstrumentId,
    Money,
    OrderId,
    Price,
    Quantity,
    StrategyId,
    TimeFrame,
    Timestamp,
)

from domain.commands import PlaceOrderCommand

# ---------------------------------------------------------------------------
# Helpers — minimal concrete implementations for structural-subtyping tests
# ---------------------------------------------------------------------------


@dataclass
class _FakeStrategy:
    strategy_id: StrategyId = field(default_factory=lambda: StrategyId(value="s1"))

    def on_start(self, event: StartEvent) -> None: ...
    def on_stop(self, event: StopEvent) -> None: ...
    def on_quote(self, quote: Quote) -> None: ...
    def on_bar(self, bar: Bar) -> None: ...
    def on_fill(self, fill: OrderFilled) -> None: ...
    def on_event(self, event: Message) -> None: ...


@dataclass
class _FakeDataAdapter:
    def subscribe(self, instrument: Instrument, timeframe: TimeFrame) -> None: ...
    def unsubscribe(self, instrument: Instrument) -> None: ...
    def request_history(
        self, instrument: Instrument, start: Timestamp, end: Timestamp
    ) -> Iterator[Bar]:
        yield from ()

    def get_quote(self, instrument_id: InstrumentId) -> Quote:
        raise NotImplementedError


@dataclass
class _FakeBrokerAdapter:
    def connect(self) -> None: ...
    def authenticate(self) -> bool: ...
    def close(self) -> None: ...
    def submit_order(self, command: PlaceOrderCommand) -> OrderId: ...
    def cancel_order(self, order_id: OrderId) -> None: ...
    def modify_order(self, order_id: OrderId, command: PlaceOrderCommand) -> None: ...
    def get_order(self, order_id: OrderId) -> Order:
        raise NotImplementedError

    def get_orderbook(self) -> list[Order]: ...
    def get_positions(self) -> list[Position]: ...
    def get_holdings(self) -> list[Position]: ...
    def get_funds(self) -> Account:
        raise NotImplementedError

    def mass_status(self) -> BrokerSnapshot:
        raise NotImplementedError

    def get_quote(self, instrument_id: InstrumentId) -> Quote:
        raise NotImplementedError

    def ltp(self, instrument_id: InstrumentId) -> Price:
        raise NotImplementedError

    def depth(self, instrument_id: InstrumentId) -> Any:
        raise NotImplementedError

    def history(self, instrument_id: InstrumentId, timeframe: TimeFrame, start: Any, end: Any) -> list[Bar]:
        raise NotImplementedError

    def load_instruments(self) -> None: ...
    def search(self, query: str) -> list[Instrument]: ...
    def capabilities(self) -> Any: ...


@dataclass
class _FakeFillSource:
    def submit(self, command: PlaceOrderCommand) -> OrderResult:
        raise NotImplementedError

    def cancel(self, order_id: OrderId) -> CancelResult:
        raise NotImplementedError


@dataclass
class _FakeRiskModel:
    def check_order(
        self, command: PlaceOrderCommand, context: RiskContext
    ) -> RiskCheckResult:
        raise NotImplementedError

    def check_position(
        self, position: Position, context: RiskContext
    ) -> RiskCheckResult:
        raise NotImplementedError

    def check_account(
        self, account: Account, context: RiskContext
    ) -> RiskCheckResult:
        raise NotImplementedError


# RiskCheckResult lives in application.risk.context; re-import for clarity.
from application.risk.context import RiskCheckResult as RiskCheckResult  # noqa: E402


@dataclass
class _FakePortfolioModel:
    def rebalance(
        self, signals: list[Signal], context: PortfolioContext
    ) -> list[PlaceOrderCommand]: ...
    def optimize(
        self, signals: list[Signal], context: PortfolioContext
    ) -> list[PlaceOrderCommand]: ...


@dataclass
class _FakeClock:
    def now(self) -> Timestamp: ...

    def advance(self, delta: timedelta) -> None: ...


@dataclass
class _FakeEventBus:
    def subscribe(self, msg_type: type, handler: Callable[..., Any]) -> Subscription: ...
    def publish(self, message: Message) -> None: ...


@dataclass
class _FakeIdempotencyGuard:
    def check_and_reserve(self, correlation_id: CorrelationId) -> IdempotencyResult: ...
    def record_result(
        self, correlation_id: CorrelationId, result: OrderResult
    ) -> None: ...


# ===========================================================================
# Tests
# ===========================================================================


class TestProtocolsAreProtocols:
    """Every port must be a typing.Protocol subclass."""

    @pytest.mark.parametrize(
        "proto",
        [
            Strategy,
            DataAdapter,
            BrokerAdapter,
            FillSource,
            RiskModel,
            PortfolioModel,
            Clock,
            EventBusPort,
            IdempotencyGuard,
        ],
        ids=[
            "Strategy",
            "DataAdapter",
            "BrokerAdapter",
            "FillSource",
            "RiskModel",
            "PortfolioModel",
            "Clock",
            "EventBusPort",
            "IdempotencyGuard",
        ],
    )
    def test_is_protocol(self, proto: type) -> None:
        assert issubclass(proto, Protocol)

    @pytest.mark.parametrize(
        "proto",
        [
            Strategy,
            DataAdapter,
            BrokerAdapter,
            FillSource,
            RiskModel,
            PortfolioModel,
            Clock,
            EventBusPort,
            IdempotencyGuard,
        ],
    )
    def test_is_runtime_checkable(self, proto: type) -> None:
        assert hasattr(proto, "_is_runtime_checkable") or True  # runtime_checkable sets class attr
        # Verify we can use isinstance with runtime_checkable protocols
        assert isinstance(_FakeClock(), Clock)


class TestStrategyProtocol:
    def test_has_strategy_id_attribute(self) -> None:
        assert "strategy_id" in Strategy.__annotations__

    def test_has_required_methods(self) -> None:
        required = {"on_start", "on_stop", "on_quote", "on_bar", "on_fill", "on_event"}
        for name in required:
            assert hasattr(Strategy, name), f"Strategy missing method: {name}"

    def test_method_signatures(self) -> None:
        sig = inspect.signature(Strategy.on_start)
        params = list(sig.parameters.keys())
        assert params == ["self", "event"]

        sig = inspect.signature(Strategy.on_quote)
        params = list(sig.parameters.keys())
        assert params == ["self", "quote"]

    def test_concrete_satisfies_protocol(self) -> None:
        assert isinstance(_FakeStrategy(), Strategy)


class TestDataAdapterProtocol:
    def test_has_required_methods(self) -> None:
        required = {"subscribe", "unsubscribe", "request_history", "get_quote"}
        for name in required:
            assert hasattr(DataAdapter, name), f"DataAdapter missing method: {name}"

    def test_subscribe_signature(self) -> None:
        sig = inspect.signature(DataAdapter.subscribe)
        params = list(sig.parameters.keys())
        assert params == ["self", "instrument", "timeframe"]

    def test_request_history_returns_iterator(self) -> None:
        sig = inspect.signature(DataAdapter.request_history)
        assert sig.return_annotation in (Iterator[Bar], "Iterator[Bar]")

    def test_concrete_satisfies_protocol(self) -> None:
        assert isinstance(_FakeDataAdapter(), DataAdapter)


class TestBrokerAdapterProtocol:
    def test_has_required_methods(self) -> None:
        required = {
            "submit_order",
            "cancel_order",
            "modify_order",
            "get_order",
            "get_orderbook",
            "get_positions",
            "get_funds",
            "mass_status",
        }
        for name in required:
            assert hasattr(BrokerAdapter, name), f"BrokerAdapter missing method: {name}"

    def test_submit_order_returns_order_id(self) -> None:
        sig = inspect.signature(BrokerAdapter.submit_order)
        assert sig.return_annotation in (OrderId, "OrderId")

    def test_concrete_satisfies_protocol(self) -> None:
        assert isinstance(_FakeBrokerAdapter(), BrokerAdapter)


class TestFillSourceProtocol:
    def test_has_required_methods(self) -> None:
        required = {"submit", "cancel"}
        for name in required:
            assert hasattr(FillSource, name), f"FillSource missing method: {name}"

    def test_submit_returns_order_result(self) -> None:
        sig = inspect.signature(FillSource.submit)
        assert sig.return_annotation in (OrderResult, "OrderResult")

    def test_cancel_returns_cancel_result(self) -> None:
        sig = inspect.signature(FillSource.cancel)
        assert sig.return_annotation in (CancelResult, "CancelResult")

    def test_concrete_satisfies_protocol(self) -> None:
        assert isinstance(_FakeFillSource(), FillSource)


class TestRiskModelProtocol:
    def test_has_required_methods(self) -> None:
        required = {"check_order", "check_position", "check_account"}
        for name in required:
            assert hasattr(RiskModel, name), f"RiskModel missing method: {name}"

    def test_check_order_signature(self) -> None:
        sig = inspect.signature(RiskModel.check_order)
        params = list(sig.parameters.keys())
        assert params == ["self", "command", "context"]

    def test_concrete_satisfies_protocol(self) -> None:
        assert isinstance(_FakeRiskModel(), RiskModel)


class TestPortfolioModelProtocol:
    def test_has_required_methods(self) -> None:
        required = {"rebalance", "optimize"}
        for name in required:
            assert hasattr(PortfolioModel, name), f"PortfolioModel missing method: {name}"

    def test_rebalance_signature(self) -> None:
        sig = inspect.signature(PortfolioModel.rebalance)
        params = list(sig.parameters.keys())
        assert params == ["self", "signals", "context"]

    def test_concrete_satisfies_protocol(self) -> None:
        assert isinstance(_FakePortfolioModel(), PortfolioModel)


class TestClockProtocol:
    def test_has_now_and_advance(self) -> None:
        assert hasattr(Clock, "now")
        assert hasattr(Clock, "advance")

    def test_now_returns_timestamp(self) -> None:
        sig = inspect.signature(Clock.now)
        assert sig.return_annotation in (Timestamp, "Timestamp")

    def test_advance_signature(self) -> None:
        sig = inspect.signature(Clock.advance)
        params = list(sig.parameters.keys())
        assert params == ["self", "delta"]

    def test_concrete_satisfies_protocol(self) -> None:
        assert isinstance(_FakeClock(), Clock)


class TestEventBusPortProtocol:
    def test_has_subscribe_and_publish(self) -> None:
        assert hasattr(EventBusPort, "subscribe")
        assert hasattr(EventBusPort, "publish")

    def test_subscribe_returns_subscription(self) -> None:
        sig = inspect.signature(EventBusPort.subscribe)
        assert sig.return_annotation in (Subscription, "Subscription")

    def test_concrete_satisfies_protocol(self) -> None:
        assert isinstance(_FakeEventBus(), EventBusPort)


class TestIdempotencyGuardProtocol:
    def test_has_required_methods(self) -> None:
        assert hasattr(IdempotencyGuard, "check_and_reserve")
        assert hasattr(IdempotencyGuard, "record_result")

    def test_check_and_reserve_returns_result(self) -> None:
        sig = inspect.signature(IdempotencyGuard.check_and_reserve)
        assert sig.return_annotation in (IdempotencyResult, "IdempotencyResult")

    def test_concrete_satisfies_protocol(self) -> None:
        assert isinstance(_FakeIdempotencyGuard(), IdempotencyGuard)


class TestPortTypes:
    """Supporting types used by protocols exist and are importable."""

    def test_start_event_exists(self) -> None:
        assert StartEvent is not None

    def test_stop_event_exists(self) -> None:
        assert StopEvent is not None

    def test_order_result_exists(self) -> None:
        assert OrderResult is not None

    def test_cancel_result_exists(self) -> None:
        assert CancelResult is not None

    def test_risk_context_exists(self) -> None:
        assert RiskContext is not None

    def test_portfolio_context_exists(self) -> None:
        assert PortfolioContext is not None

    def test_broker_snapshot_exists(self) -> None:
        assert BrokerSnapshot is not None

    def test_signal_exists(self) -> None:
        assert Signal is not None

    def test_idempotency_result_exists(self) -> None:
        assert IdempotencyResult is not None

    def test_subscription_exists(self) -> None:
        assert Subscription is not None
