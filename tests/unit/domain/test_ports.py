"""Tests for domain port protocols — fresh implementation.

Verifies:
- All protocols are defined and importable
- runtime_checkable works (isinstance checks)
- Concrete implementations satisfy protocols
- Frozen dataclasses are immutable
"""

from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4


# ── Protocol imports ──────────────────────────────────────────────────
from domain.ports.strategy import Strategy
from domain.ports.broker_adapter import (
    BrokerAdapter,
    BrokerSnapshot,
    OrderResult as BrokerOrderResult,
)
from domain.ports.fill_source import (
    FillSource,
    OrderResult as FillOrderResult,
    CancelResult,
)
from domain.ports.risk_model import RiskModel, RiskCheckResult, RiskContext
from domain.ports.event_bus import EventBusPort, Subscription
from domain.ports.clock import Clock
from domain.ports.portfolio import PortfolioModel, Signal, PortfolioContext


# ── Domain imports for fakes ──────────────────────────────────────────
from domain.value_objects import Money
from domain.entities import Quote, Instrument
from domain.events.types import DomainEvent
from domain.instruments.instrument_id import InstrumentId


# ─────────────────────────────────────────────────────────────────────
#  Helpers — minimal fakes that satisfy each protocol
# ─────────────────────────────────────────────────────────────────────


class FakeStrategy:
    """Minimal Strategy implementation."""

    strategy_id = "test-strategy"

    def on_start(self, event) -> None:
        pass

    def on_stop(self, event) -> None:
        pass

    def on_quote(self, quote) -> None:
        pass

    def on_bar(self, bar) -> None:
        pass

    def on_fill(self, fill) -> None:
        pass

    def on_event(self, event) -> None:
        pass


class FakeBrokerAdapter:
    """Minimal BrokerAdapter implementation."""

    broker_id = "fake-broker"
    is_connected = False

    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def place_order(self, command) -> BrokerOrderResult:
        return BrokerOrderResult(order_id="oid-1", success=True)

    def cancel_order(self, order_id) -> BrokerOrderResult:
        return BrokerOrderResult(order_id=order_id, success=True)

    def get_quote(self, instrument_id) -> Quote:
        return Quote(symbol="TEST", exchange="NSE", ltp=Decimal("100"))

    def get_positions(self) -> list:
        return []

    def get_funds(self) -> object:
        return object()

    def mass_status(self) -> BrokerSnapshot:
        return BrokerSnapshot(orders=(), positions=(), funds=object())

    def load_instruments(self) -> None:
        pass

    def capabilities(self) -> object:
        return object()


class FakeFillSource:
    """Minimal FillSource implementation."""

    def submit(self, command) -> FillOrderResult:
        return FillOrderResult(order_id="oid-1", success=True)

    def cancel(self, order_id) -> CancelResult:
        return CancelResult(success=True)


class FakeRiskModel:
    """Minimal RiskModel implementation."""

    def check_order(self, command, context) -> RiskCheckResult:
        return RiskCheckResult(approved=True)


class FakeEventBus:
    """Minimal EventBusPort implementation."""

    def __init__(self):
        self._subs: dict[UUID, tuple] = {}

    def subscribe(self, msg_type, handler) -> Subscription:
        sub = Subscription()
        self._subs[sub.subscription_id] = (msg_type, handler)
        return sub

    def unsubscribe(self, subscription: Subscription) -> None:
        self._subs.pop(subscription.subscription_id, None)

    def publish(self, message) -> None:
        pass


class FakeClock:
    """Minimal Clock implementation."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FakePortfolioModel:
    """Minimal PortfolioModel implementation."""

    def rebalance(self, signals, context) -> list:
        return []


# ─────────────────────────────────────────────────────────────────────
#  Tests
# ─────────────────────────────────────────────────────────────────────


class TestProtocolDefinitions:
    """All protocols exist and are Protocol subclasses."""

    def test_strategy_is_protocol(self):
        assert issubclass(Strategy, Protocol)

    def test_broker_adapter_is_protocol(self):
        assert issubclass(BrokerAdapter, Protocol)

    def test_fill_source_is_protocol(self):
        assert issubclass(FillSource, Protocol)

    def test_risk_model_is_protocol(self):
        assert issubclass(RiskModel, Protocol)

    def test_event_bus_port_is_protocol(self):
        assert issubclass(EventBusPort, Protocol)

    def test_clock_is_protocol(self):
        assert issubclass(Clock, Protocol)

    def test_portfolio_model_is_protocol(self):
        assert issubclass(PortfolioModel, Protocol)


class TestRuntimeCheckable:
    """runtime_checkable enables isinstance() checks."""

    def test_strategy_isinstance(self):
        assert isinstance(FakeStrategy(), Strategy)

    def test_broker_adapter_isinstance(self):
        assert isinstance(FakeBrokerAdapter(), BrokerAdapter)

    def test_fill_source_isinstance(self):
        assert isinstance(FakeFillSource(), FillSource)

    def test_risk_model_isinstance(self):
        assert isinstance(FakeRiskModel(), RiskModel)

    def test_event_bus_isinstance(self):
        assert isinstance(FakeEventBus(), EventBusPort)

    def test_clock_isinstance(self):
        assert isinstance(FakeClock(), Clock)

    def test_portfolio_model_isinstance(self):
        assert isinstance(FakePortfolioModel(), PortfolioModel)

    def test_non_implementer_fails(self):
        class NotAStrategy:
            pass

        assert not isinstance(NotAStrategy(), Strategy)


class TestFrozenDataclasses:
    """Data classes are frozen (immutable)."""

    def test_order_result_frozen(self):
        r = FillOrderResult(order_id="oid-1", success=True)
        with pytest.raises(FrozenInstanceError):
            r.success = False

    def test_cancel_result_frozen(self):
        r = CancelResult(success=True, message="ok")
        with pytest.raises(FrozenInstanceError):
            r.success = False

    def test_risk_check_result_frozen(self):
        r = RiskCheckResult(approved=True, reason="ok")
        with pytest.raises(FrozenInstanceError):
            r.approved = False

    def test_signal_frozen(self):
        s = Signal(instrument_id="X", direction=1, strength=0.8)
        with pytest.raises(FrozenInstanceError):
            s.direction = -1

    def test_subscription_has_id(self):
        s = Subscription()
        assert isinstance(s.subscription_id, UUID)

    def test_broker_snapshot_frozen(self):
        bs = BrokerSnapshot(orders=(), positions=(), funds=object())
        with pytest.raises(FrozenInstanceError):
            bs.orders = ()


class TestProtocolMethodSignatures:
    """Protocols have the expected methods."""

    def test_strategy_methods(self):
        expected = {"on_start", "on_stop", "on_quote", "on_bar", "on_fill", "on_event"}
        actual = {m for m in dir(Strategy) if not m.startswith("_")}
        # Check at least the required methods exist
        # (Protocol may expose additional attributes)
        assert expected.issubset(actual) or expected <= set(dir(Strategy))

    def test_clock_has_now(self):
        assert hasattr(Clock, "now")

    def test_event_bus_has_subscribe_publish(self):
        assert hasattr(EventBusPort, "subscribe")
        assert hasattr(EventBusPort, "publish")
        assert hasattr(EventBusPort, "unsubscribe")
