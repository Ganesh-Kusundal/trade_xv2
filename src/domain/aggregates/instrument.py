"""Instrument Aggregate Root — the central abstraction for the entire system.

InstrumentAggregate replaces the anemic ``Instrument`` dataclass with a
rich domain object that owns identity and state, delegates behavior to
injected providers, and exposes capabilities through a clean extension
system.

Design Principles:
    - Composition over inheritance (providers are injected, not inherited)
    - Single responsibility (Instrument owns identity + state only)
    - Open/Closed (extensions add capabilities without modification)
    - Thread-safe state (atomic replacement via internal lock)

This is a REPLACEMENT for the old Instrument entity, not a wrapper.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pandas as pd

from domain.entities.market import MarketDepth, QuoteSnapshot
from domain.entities.options import FutureChain, OptionChain
from domain.extensions.base import Extension
from domain.instruments.instrument_id import InstrumentId
from domain.value_objects.capability import Capability
from domain.value_objects.state import InstrumentState, SubscriptionState

if TYPE_CHECKING:
    from domain.ports.protocols import DataProvider, ExecutionProvider, Subscription


class InstrumentAggregate:
    """Instrument Aggregate Root — the central abstraction.

    Owns:
        - Identity (InstrumentId)
        - State (InstrumentState) — thread-safe internal mutation

    Delegates to:
        - DataProvider for market data
        - Extensions for broker-specific features

    Does NOT own:
        - Execution (OMS / ExecutionService owns that)
        - Historical data storage (provider does)
        - Order management (OMS does)
        - Analytics computation (analytics engines do)

    Thread Safety:
        State mutations are atomic — the entire InstrumentState is replaced
        under an RLock.  Reads are lock-free (state is immutable).
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        *,
        data_provider: DataProvider | None = None,
        extensions: list[Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        instrument_id:
            Canonical instrument identity (the only required argument).
        data_provider:
            Object satisfying the DataProvider protocol.  Injected at
            composition root, never imported by domain code.
        extensions:
            List of Extension objects available for this instrument.
        metadata:
            Static instrument metadata (lot_size, tick_size, name, etc.).
        """
        self._id = instrument_id
        self._data_provider = data_provider
        self._extensions: list[Extension] = list(extensions or [])
        self._metadata: dict[str, Any] = dict(metadata or {})
        self._state = InstrumentState()
        self._subscription = None
        self._lock = threading.RLock()

    # ── Identity (read-only, lock-free) ────────────────────────────

    @property
    def id(self) -> InstrumentId:
        """Canonical instrument identity."""
        return self._id

    @property
    def symbol(self) -> str:
        """Underlying symbol (e.g., ``"RELIANCE"``)."""
        return self._id.underlying

    @property
    def exchange(self) -> str:
        """Exchange code (e.g., ``"NSE"``)."""
        return self._id.exchange

    @property
    def asset_type(self) -> str:
        """Asset type: EQUITY, INDEX, FUTURES, OPTIONS."""
        return self._id.asset_type

    @property
    def is_equity(self) -> bool:
        return self._id.is_equity

    @property
    def is_index(self) -> bool:
        return self._id.is_index

    @property
    def is_future(self) -> bool:
        return self._id.is_future

    @property
    def is_option(self) -> bool:
        return self._id.is_option

    # ── Metadata (read-only) ───────────────────────────────────────

    @property
    def lot_size(self) -> int:
        """Minimum tradeable quantity."""
        return self._metadata.get("lot_size", 1)

    @property
    def tick_size(self) -> Decimal:
        """Minimum price movement."""
        raw = self._metadata.get("tick_size")
        return Decimal(str(raw)) if raw is not None else Decimal("0.05")

    @property
    def name(self) -> str | None:
        """Human-readable name."""
        return self._metadata.get("name")

    @property
    def metadata(self) -> dict[str, Any]:
        """All static metadata (read-only copy)."""
        return dict(self._metadata)

    # ── State (thread-safe read) ───────────────────────────────────

    @property
    def state(self) -> InstrumentState:
        """Current instrument state (immutable snapshot)."""
        return self._state

    @property
    def quote(self) -> QuoteSnapshot | None:
        """Latest QuoteSnapshot, or None if not yet fetched."""
        return self._state.quote

    @property
    def depth(self) -> MarketDepth | None:
        """Latest MarketDepth, or None if not yet fetched."""
        return self._state.depth

    @property
    def is_subscribed(self) -> bool:
        """True when the instrument has an active live subscription."""
        return self._state.is_subscribed

    @property
    def subscription(self) -> SubscriptionState:
        """Current subscription state."""
        return self._state.subscription

    @property
    def last_update(self) -> datetime | None:
        """Timestamp of last state update."""
        return self._state.last_update

    @property
    def error(self) -> str | None:
        """Last error message, or None."""
        return self._state.error

    # ── Data Operations (delegated to provider) ────────────────────

    def get_quote(self) -> QuoteSnapshot | None:
        """Fetch latest quote from provider and update state.

        Returns the QuoteSnapshot, or None if the provider is unavailable.
        Propagates provider exceptions — callers must handle errors.
        """
        if self._data_provider is None:
            return None
        quote = self._data_provider.get_quote(self._id)
        if quote is not None:
            with self._lock:
                self._state = self._state.with_quote(quote)
        return quote

    def get_history(
        self,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV from provider.

        Returns an empty DataFrame if no provider is configured.
        Propagates provider exceptions.
        """
        if self._data_provider is None:
            return pd.DataFrame()
        return self._data_provider.get_history(
            self._id,
            timeframe=timeframe,
            lookback_days=lookback_days,
            from_date=from_date,
            to_date=to_date,
        )

    def get_depth(self) -> MarketDepth | None:
        """Fetch market depth from provider and update state.

        Returns MarketDepth, or None if unavailable.
        Propagates provider exceptions.
        """
        if self._data_provider is None:
            return None
        depth = self._data_provider.get_depth(self._id)
        if depth is not None:
            with self._lock:
                self._state = self._state.with_depth(depth)
        return depth

    def get_option_chain(self, expiry: date | None = None) -> OptionChain:
        """Fetch option chain for this instrument (must be an underlying).

        Returns an empty OptionChain if no provider is configured.
        Propagates provider exceptions.
        """
        if self._data_provider is None:
            return OptionChain(underlying=self.symbol, exchange=self.exchange, expiry="")
        return self._data_provider.get_option_chain(self._id, expiry=expiry)

    def get_future_chain(self) -> FutureChain:
        """Fetch futures chain for this instrument (must be an underlying).

        Returns an empty FutureChain if no provider is configured.
        Propagates provider exceptions.
        """
        if self._data_provider is None:
            return FutureChain(underlying=self.symbol, exchange=self.exchange)
        return self._data_provider.get_future_chain(self._id)

    # ── Subscription (delegated to provider) ───────────────────────

    def subscribe(
        self,
        callback: Callable[[InstrumentId, Any], None],
        *,
        depth: bool = False,
    ) -> Subscription | None:
        """Subscribe to live market data.

        Parameters
        ----------
        callback:
            Called as ``callback(instrument_id, quote_snapshot)`` on each tick.
        depth:
            If True, also subscribe to market depth updates.

        Returns the Subscription handle, or None if no provider.
        Propagates provider exceptions.
        """
        if self._data_provider is None:
            return None

        from domain.value_objects.state import SubscriptionStatus

        # Transition to SUBSCRIBING
        with self._lock:
            self._state = self._state.with_subscription(
                SubscriptionState(
                    status=SubscriptionStatus.SUBSCRIBING,
                    symbol=self.symbol,
                    exchange=self.exchange,
                )
            )

        subscription = self._data_provider.subscribe(
            self._id,
            callback,
            depth=depth,
        )
        self._subscription = subscription

        # Transition to SUBSCRIBED
        with self._lock:
            self._state = self._state.with_subscription(
                SubscriptionState(
                    status=SubscriptionStatus.SUBSCRIBED,
                    symbol=self.symbol,
                    exchange=self.exchange,
                    started_at=datetime.now(timezone.utc),
                )
            )
        return subscription

    def unsubscribe(self) -> None:
        """Tear down the live subscription and transition state to UNSUBSCRIBED.

        Cancels the underlying provider subscription (if any) and atomically
        flips the owned ``InstrumentState`` so ``is_subscribed`` becomes False.
        """
        if self._subscription is not None and self._data_provider is not None:
            try:
                self._data_provider.unsubscribe(self._subscription)
            except Exception:
                pass
        self._subscription = None
        with self._lock:
            self._state = self._state.with_unsubscribed()

    def mark_error(self, error: str) -> None:
        """Mark the instrument as having an error (called by providers/services)."""
        with self._lock:
            self._state = self._state.with_error(error)

    # ── Extensions (composed, not inherited) ───────────────────────

    def has_extension(self, name: str) -> bool:
        """Check if this instrument has a named extension."""
        return any(ext.name == name for ext in self._extensions)

    def get_extension(self, name: str) -> Extension | None:
        """Get a named extension, or None."""
        return next(
            (ext for ext in self._extensions if ext.name == name),
            None,
        )

    @property
    def extensions(self) -> list[Extension]:
        """All available extensions for this instrument."""
        return list(self._extensions)

    @property
    def capabilities(self) -> list[Capability]:
        """All capabilities from registered extensions."""
        caps: list[Capability] = []
        for ext in self._extensions:
            caps.extend(ext.capabilities)
        return caps

    def capability_names(self) -> list[str]:
        """List all capability names available for this instrument."""
        return [c.name for c in self.capabilities]

    # ── Representation ─────────────────────────────────────────────

    def __repr__(self) -> str:
        provider_name = self._data_provider.name if self._data_provider else "None"
        ext_names = [e.name for e in self._extensions]
        return (
            f"InstrumentAggregate({self._id}, "
            f"provider={provider_name}, "
            f"extensions={ext_names})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, InstrumentAggregate):
            return NotImplemented
        return self._id == other._id

    def __hash__(self) -> int:
        return hash(self._id)
