"""Universe & Session — the public entry point into the domain model.

A :class:`Session` is the composition root: it binds a concrete ``DataProvider``
(and optional ``DomainEventBus``) once, wires it as the platform default, and
exposes a :class:`Universe` for building instruments.

    session = Session(provider)
    reliance = session.universe.equity("RELIANCE")   # Equity
    chain = reliance.option_chain("2026-07-31")      # OptionChain

No broker, REST, WebSocket, or JSON concept appears here.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from domain.instruments.instrument import Equity, Future, Index, Instrument, Option
from domain.instruments.instrument_id import InstrumentId
from domain.ports.provider_registry import set_default_provider

if TYPE_CHECKING:
    from domain.events.bus import DomainEventBus
    from domain.ports.protocols import DataProvider


class Universe:
    """Builds domain instruments from symbols. Broker-free by design."""

    def __init__(
        self,
        provider: "DataProvider",
        *,
        event_bus: "DomainEventBus | None" = None,
    ) -> None:
        self._provider = provider
        self._event_bus = event_bus

    def equity(self, symbol: str, exchange: str = "NSE") -> Equity:
        return Equity(symbol, exchange, provider=self._provider, event_bus=self._event_bus)

    def index(self, name: str, exchange: str = "NSE") -> Index:
        return Index(name, exchange, provider=self._provider, event_bus=self._event_bus)

    def future(self, symbol: str, *, expiry: date, exchange: str = "NFO") -> Future:
        return Future(
            symbol, exchange, expiry=expiry, provider=self._provider, event_bus=self._event_bus
        )

    def option(
        self,
        underlying: str,
        strike: Any,
        right: str,
        *,
        expiry: date,
        exchange: str = "NFO",
        leg: Any | None = None,
    ) -> Option:
        iid = InstrumentId.option(exchange, underlying, expiry, strike, right)
        return Option(
            iid,
            strike=strike,
            expiry=expiry,
            right=right,
            provider=self._provider,
            leg=leg,
            event_bus=self._event_bus,
        )

    def get(self, instrument_id: InstrumentId) -> Instrument:
        return Instrument(instrument_id, data_provider=self._provider, event_bus=self._event_bus)


class Session:
    """Composition root. Binds provider + event bus and exposes the universe."""

    def __init__(
        self,
        provider: "DataProvider",
        *,
        event_bus: "DomainEventBus | None" = None,
    ) -> None:
        self._provider = provider
        self._event_bus = event_bus
        set_default_provider(provider)
        self._universe = Universe(provider, event_bus=event_bus)

    @property
    def universe(self) -> Universe:
        return self._universe

    @property
    def provider(self) -> "DataProvider":
        return self._provider

    @property
    def event_bus(self) -> "DomainEventBus | None":
        return self._event_bus

    def close(self) -> None:
        set_default_provider(None)
