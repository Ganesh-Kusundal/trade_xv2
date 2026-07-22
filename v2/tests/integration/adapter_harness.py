"""Reusable AdapterTestHarness for venue plugins (paper / dhan / upstox)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from domain.commands import PlaceOrderCommand
from domain.entities import Account, Position, Quote
from domain.value_objects import InstrumentId, OrderId


class _BrokerSurface(Protocol):
    def connect(self) -> None: ...

    def close(self) -> None: ...

    def get_quote(self, instrument_id: InstrumentId) -> Quote: ...

    def place_order(self, command: PlaceOrderCommand) -> OrderId: ...

    def cancel_order(self, order_id: OrderId) -> None: ...

    def get_positions(self) -> list[Position]: ...

    def get_funds(self) -> Account: ...

    def mass_status(self) -> Any: ...

    def capabilities(self) -> Any: ...


@dataclass
class AdapterTestHarness:
    """Thin contract checks against a real broker gateway — no mocks."""

    adapter: _BrokerSurface

    def test_connect(self) -> None:
        self.adapter.connect()
        self.adapter.close()
        self.adapter.connect()

    def test_get_quote(self, instrument_id: InstrumentId) -> Quote:
        quote = self.adapter.get_quote(instrument_id)
        assert isinstance(quote, Quote)
        assert quote.instrument_id == instrument_id
        assert quote.bid.value <= quote.ask.value
        return quote

    def test_place_fill(self, command: PlaceOrderCommand) -> OrderId:
        """Paper fills immediately; live harnesses may use place_and_cancel instead."""
        order_id = self.adapter.place_order(command)
        assert isinstance(order_id, OrderId)
        assert order_id.value
        return order_id

    def test_get_positions(self) -> list[Position]:
        positions = self.adapter.get_positions()
        assert isinstance(positions, list)
        return positions

    def test_get_funds(self) -> Account:
        account = self.adapter.get_funds()
        assert isinstance(account, Account)
        return account

    def test_mass_status(self) -> Any:
        snap = self.adapter.mass_status()
        assert snap is not None
        return snap

    def test_capabilities(self) -> Any:
        caps = self.adapter.capabilities()
        assert caps is not None
        return caps
