"""Instrument — the public domain object (Layer Zero).

This is what a trader interacts with:

    nifty = Equity("NIFTY")
    nifty.ltp
    nifty.quote
    nifty.history("5m")
    nifty.subscribe()

It wraps :class:`domain.aggregates.instrument.InstrumentAggregate`, which owns
identity + state and delegates data to an injected ``DataProvider``. The broker
is never referenced here — it lives behind the provider, set at the composition
root. No ``brokers`` import appears anywhere in this module.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pandas as pd

from domain.aggregates.instrument import InstrumentAggregate
from domain.entities.market import MarketDepth, QuoteSnapshot
from domain.entities.options import FutureChain, OptionChain as OptionChainVO
from domain.instruments.instrument_id import InstrumentId

if TYPE_CHECKING:
    from collections.abc import Callable
    from domain.events.bus import DomainEventBus
    from domain.instruments.subscription import Subscription
    from domain.ports.protocols import DataProvider

    from domain.options.option_chain import OptionChain


def _parse_expiry(exp: date | str | None) -> date | None:
    if isinstance(exp, date):
        return exp
    if isinstance(exp, str):
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(exp, fmt).date()
            except ValueError:
                continue
    return None


class Instrument:
    """Aggregate-root facade for any tradable instrument.

    Owns: identity (InstrumentId), live state (via the wrapped aggregate).
    Delegates: data/execution to the injected provider.
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        *,
        data_provider: "DataProvider | None" = None,
        metadata: dict[str, Any] | None = None,
        event_bus: "DomainEventBus | None" = None,
    ) -> None:
        from domain.ports.provider_registry import get_default_provider

        self._provider = data_provider or get_default_provider()
        self._aggregate = InstrumentAggregate(
            instrument_id,
            data_provider=self._provider,
            metadata=metadata,
        )
        self._subscription: "Subscription | None" = None
        self._event_bus = event_bus

    # ── Identity (lock-free read-through) ───────────────────────────

    @property
    def id(self) -> InstrumentId:
        return self._aggregate.id

    @property
    def symbol(self) -> str:
        return self._aggregate.symbol

    @property
    def exchange(self) -> str:
        return self._aggregate.exchange

    @property
    def asset_type(self) -> str:
        return self._aggregate.asset_type

    @property
    def lot_size(self) -> int:
        return self._aggregate.lot_size

    @property
    def tick_size(self) -> Decimal:
        return self._aggregate.tick_size

    # ── Live state (reads through the aggregate's owned state) ──────

    @property
    def quote(self) -> QuoteSnapshot | None:
        return self._aggregate.quote

    @property
    def ltp(self) -> Decimal | None:
        q = self._aggregate.quote
        return q.ltp if q else None

    @property
    def bid(self) -> Decimal | None:
        q = self._aggregate.quote
        return q.bid if q else None

    @property
    def ask(self) -> Decimal | None:
        q = self._aggregate.quote
        return q.ask if q else None

    @property
    def volume(self) -> int:
        q = self._aggregate.quote
        return q.volume if q else 0

    @property
    def market_depth(self) -> MarketDepth | None:
        return self._aggregate.depth

    @property
    def order_book(self) -> MarketDepth | None:
        return self._aggregate.depth

    @property
    def is_live(self) -> bool:
        return self._aggregate.is_subscribed

    @property
    def aggregate(self) -> InstrumentAggregate:
        """Escape hatch to the underlying aggregate (identity/state)."""
        return self._aggregate

    # ── Extensions (broker-specific capability plugins) ──────────────

    def has_extension(self, name: str) -> bool:
        """Check if a named broker extension is available."""
        return self._aggregate.has_extension(name)

    def get_extension(self, name: str):
        """Get a named broker extension, or None.

        Example::

            depth = inst.get_extension("depth20")
            if depth:
                depth.full_depth()
        """
        return self._aggregate.get_extension(name)

    @property
    def extensions(self):
        """All available broker extensions for this instrument."""
        return self._aggregate.extensions

    @property
    def indicators(self):
        from domain.indicators.indicators import Indicators
        return Indicators(self)

    # ── Behaviors (Tell, Don't Ask) ─────────────────────────────────

    def refresh(self) -> QuoteSnapshot | None:
        """Pull the latest quote into state and return it."""
        quote = self._aggregate.get_quote()
        if self._event_bus is not None and quote is not None:
            self._event_bus.publish(
                "QUOTE_UPDATED",
                {"symbol": self.symbol, "exchange": self.exchange, "ltp": str(quote.ltp)},
            )
        return quote

    def history(
        self,
        *,
        timeframe: str = "1D",
        days: int = 120,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """Historical OHLCV, attached to this instrument."""
        return self._aggregate.get_history(
            timeframe=timeframe,
            lookback_days=days,
            from_date=start,
            to_date=end,
        )

    def depth(self) -> MarketDepth | None:
        return self._aggregate.get_depth()

    def spread(self) -> Decimal | None:
        if self.bid is not None and self.ask is not None:
            return self.ask - self.bid
        return None

    def mid_price(self) -> Decimal | None:
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return None

    def subscribe(
        self,
        callback: "Callable[[InstrumentId, Any], None]",
        *,
        depth: bool = False,
    ) -> "Subscription | None":
        """Subscribe to live data. Returns a tracked Subscription handle.

        Each incoming tick/depth is published as a TICK / DEPTH_UPDATED domain
        event through the injected event bus.
        """
        from domain.events.types import EventType
        from domain.instruments.subscription import Subscription

        subscription = Subscription(self.id, event_bus=self._event_bus, depth=depth)

        def _wrapped(iid: InstrumentId, payload: Any) -> None:
            subscription._on_tick(iid, payload)
            if callback is not None:
                callback(iid, payload)

        provider_sub = self._aggregate.subscribe(_wrapped, depth=depth)
        if provider_sub is None:
            return None
        subscription._attach(provider_sub, teardown=self._aggregate.unsubscribe)
        if self._event_bus is not None:
            self._event_bus.publish(
                EventType.SUBSCRIPTION_STARTED,
                {"symbol": self.symbol, "exchange": self.exchange, "depth": depth},
            )
        self._subscription = subscription
        return subscription

    def unsubscribe(self) -> None:
        if self._subscription is not None:
            self._subscription.unsubscribe()
            self._subscription = None
        else:
            self._aggregate.unsubscribe()

    def option_chain(self, expiry: date | None = None) -> "OptionChain":
        """Return this instrument's option chain as a rich domain object."""
        from domain.options.option_chain import OptionChain

        vo: OptionChainVO = self._aggregate.get_option_chain(expiry=expiry)
        return OptionChain(vo, provider=self._provider)

    def future_chain(self) -> FutureChain:
        return self._aggregate.get_future_chain()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.id})"


class Equity(Instrument):
    """Equity instrument. ``Equity("RELIANCE")``."""

    def __init__(
        self,
        symbol: str,
        exchange: str = "NSE",
        *,
        provider: "DataProvider | None" = None,
        metadata: dict[str, Any] | None = None,
        event_bus: "DomainEventBus | None" = None,
    ) -> None:
        super().__init__(
            InstrumentId.equity(exchange, symbol),
            data_provider=provider,
            metadata=metadata,
            event_bus=event_bus,
        )


class Index(Instrument):
    """Index instrument. ``Index("NIFTY")``."""

    def __init__(
        self,
        name: str,
        exchange: str = "NSE",
        *,
        provider: "DataProvider | None" = None,
        metadata: dict[str, Any] | None = None,
        event_bus: "DomainEventBus | None" = None,
    ) -> None:
        super().__init__(
            InstrumentId.index(exchange, name),
            data_provider=provider,
            metadata=metadata,
            event_bus=event_bus,
        )


class Future(Instrument):
    """Futures instrument. ``Future("NIFTY", expiry=date(...))``.

    Basis / cost-of-carry are computed by a pricing engine adapter (future
    work) and exposed here once available; signatures are present now.
    """

    def __init__(
        self,
        symbol: str,
        exchange: str = "NFO",
        *,
        expiry: date,
        provider: "DataProvider | None" = None,
        metadata: dict[str, Any] | None = None,
        event_bus: "DomainEventBus | None" = None,
    ) -> None:
        super().__init__(
            InstrumentId.future(exchange, symbol, expiry),
            data_provider=provider,
            metadata=metadata,
            event_bus=event_bus,
        )
        self._expiry = expiry

    @property
    def expiry(self) -> date:
        return self._expiry

    def basis(self) -> Decimal | None:
        return None  # pricing-engine responsibility

    def cost_of_carry(self) -> Decimal | None:
        return None  # pricing-engine responsibility


class Option(Instrument):
    """Option instrument. Usually built from a chain leg, not by hand.

    ``Option.from_leg(...)`` constructs one carrying its greeks/IV from the
    chain snapshot, so ``chain.atm.greeks.delta`` works out of the box.
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        *,
        strike: Decimal,
        expiry: date | None,
        right: str,
        provider: "DataProvider | None" = None,
        leg: Any | None = None,
        metadata: dict[str, Any] | None = None,
        event_bus: "DomainEventBus | None" = None,
    ) -> None:
        super().__init__(instrument_id, data_provider=provider, metadata=metadata, event_bus=event_bus)
        self._strike = strike
        self._expiry = expiry
        self._right = right
        self._leg = leg

    @property
    def strike(self) -> Decimal:
        return self._strike

    @property
    def expiry(self) -> date | None:
        return self._expiry

    @property
    def right(self) -> str:
        return self._right

    @property
    def is_call(self) -> bool:
        return self._right == "CE"

    @property
    def greeks(self):
        from domain.options.greeks import Greeks

        leg_greeks = getattr(self._leg, "greeks", None)
        return Greeks.from_dict(leg_greeks) if leg_greeks else Greeks.zero()

    @property
    def iv(self):
        return getattr(self._leg, "iv", None)

    @classmethod
    def from_leg(
        cls,
        underlying: str,
        exchange: str,
        expiry: date | str | None,
        strike: Decimal,
        right: str,
        leg: Any,
        *,
        provider: "DataProvider | None" = None,
    ) -> "Option":
        exp = _parse_expiry(expiry)
        iid = InstrumentId.option(exchange, underlying, exp, strike, right)
        return cls(
            iid,
            strike=strike,
            expiry=exp,
            right=right,
            provider=provider,
            leg=leg,
        )
