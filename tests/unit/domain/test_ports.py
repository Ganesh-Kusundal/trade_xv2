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




# ─────────────────────────────────────────────────────────────────────
#  Tests
# ─────────────────────────────────────────────────────────────────────


class TestProtocolDefinitions:
    """All protocols exist and are Protocol subclasses."""

    def test_strategy_is_protocol(self):
        assert issubclass(Strategy, Protocol)

    def test_broker_adapter_is_protocol(self):
        assert issubclass(BrokerAdapter, Protocol)


class TestRuntimeCheckable:
    """runtime_checkable enables isinstance() checks."""

    def test_strategy_isinstance(self):
        assert isinstance(FakeStrategy(), Strategy)

    def test_broker_adapter_isinstance(self):
        assert isinstance(FakeBrokerAdapter(), BrokerAdapter)

    def test_non_implementer_fails(self):
        class NotAStrategy:
            pass

        assert not isinstance(NotAStrategy(), Strategy)


class TestFrozenDataclasses:
    """Data classes are frozen (immutable)."""

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


