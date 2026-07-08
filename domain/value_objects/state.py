"""Instrument and subscription state value objects.

These capture the ephemeral runtime state of an instrument — what is
the latest quote, is it subscribed to a live feed, when was it last
updated.  The Aggregate replaces the entire state atomically (thread-safe).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.entities.market import MarketDepth, QuoteSnapshot


class SubscriptionStatus(str, Enum):
    """Lifecycle of a market-data subscription."""

    UNSUBSCRIBED = "UNSUBSCRIBED"
    SUBSCRIBING = "SUBSCRIBING"
    SUBSCRIBED = "SUBSCRIBED"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class SubscriptionState:
    """Current subscription state for an instrument — Value Object.

    Immutable snapshot.  The Aggregate replaces the entire object
    atomically when the subscription status changes.
    """

    status: SubscriptionStatus = SubscriptionStatus.UNSUBSCRIBED
    symbol: str = ""
    exchange: str = ""
    started_at: datetime | None = None
    error: str | None = None

    @property
    def is_active(self) -> bool:
        """True when the subscription is live and healthy."""
        return self.status == SubscriptionStatus.SUBSCRIBED

    @property
    def uptime_seconds(self) -> float | None:
        """Seconds since subscription started, or None if not subscribed."""
        if self.started_at is None:
            return None
        now = datetime.now(timezone.utc)
        return (now - self.started_at).total_seconds()

    def with_status(
        self,
        status: SubscriptionStatus,
        *,
        symbol: str | None = None,
        exchange: str | None = None,
        started_at: datetime | None = None,
        error: str | None = None,
    ) -> SubscriptionState:
        """Return a new state with the given status and optional field overrides."""
        return SubscriptionState(
            status=status,
            symbol=symbol if symbol is not None else self.symbol,
            exchange=exchange if exchange is not None else self.exchange,
            started_at=started_at if started_at is not None else self.started_at,
            error=error if error is not None else self.error,
        )


@dataclass(frozen=True, slots=True)
class InstrumentState:
    """Current runtime state of an instrument — Value Object.

    Captures the latest quote, depth, and subscription status in a single
    immutable snapshot.  The InstrumentAggregate replaces the entire
    ``InstrumentState`` atomically, so consumers always see a consistent view.

    This replaces the scattered state that previously lived across gateway
    objects, websocket adapters, and cache layers.
    """

    # All fields are optional — an instrument may not have a quote yet.
    quote: QuoteSnapshot | None = None
    depth: MarketDepth | None = None

    subscription: SubscriptionState = field(default_factory=SubscriptionState)
    last_update: datetime | None = None
    error: str | None = None

    @property
    def is_subscribed(self) -> bool:
        """True when the instrument has an active live subscription."""
        return self.subscription.is_active

    @property
    def age_seconds(self) -> float | None:
        """Seconds since last state update, or None if never updated."""
        if self.last_update is None:
            return None
        now = datetime.now(timezone.utc)
        return (now - self.last_update).total_seconds()

    def with_quote(self, quote: QuoteSnapshot) -> InstrumentState:
        """Return a new state with an updated quote snapshot."""
        return InstrumentState(
            quote=quote,
            depth=self.depth,
            subscription=self.subscription,
            last_update=datetime.now(timezone.utc),
            error=None,
        )

    def with_depth(self, depth: MarketDepth) -> InstrumentState:
        """Return a new state with an updated depth snapshot."""
        return InstrumentState(
            quote=self.quote,
            depth=depth,
            subscription=self.subscription,
            last_update=datetime.now(timezone.utc),
            error=None,
        )

    def with_error(self, error: str) -> InstrumentState:
        """Return a new state with an error."""
        return InstrumentState(
            quote=self.quote,
            depth=self.depth,
            subscription=self.subscription,
            last_update=self.last_update,
            error=error,
        )

    def with_subscription(self, subscription: SubscriptionState) -> InstrumentState:
        """Return a new state with an updated subscription."""
        return InstrumentState(
            quote=self.quote,
            depth=self.depth,
            subscription=subscription,
            last_update=self.last_update,
            error=None,
        )
