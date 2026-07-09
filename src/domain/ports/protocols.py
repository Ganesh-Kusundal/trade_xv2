"""Provider protocols — the central data/execution abstraction.

These protocols replace scattered broker references with a single,
unified interface.  Every module that needs market data or order
execution depends on these protocols, not on concrete broker code.

The key insight: the same Instrument should work regardless of whether
the data source is a live broker, CSV file, replay engine, or cache.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import pandas as pd
    from domain.entities.options import FutureChain, OptionChain
    from domain.entities.account import Balance, Holding
    from domain.entities.order import Order, OrderResponse
    from domain.entities.market import MarketDepth, QuoteSnapshot
    from domain.entities.position import Position
    from domain.instruments.instrument_id import InstrumentId
    from domain.candles.historical import HistoricalBar, HistoricalSeries
    from domain.orders.requests import ModifyOrderRequest, OrderRequest


class OrderResult:
    """Order operation result — wraps broker response with success/error."""
    def __init__(self, success: bool = False, order: Order | OrderResponse | None = None, error: str = "") -> None:
        self.success = success
        self.order = order
        self.error = error

    @classmethod
    def ok(cls, order: Order | OrderResponse) -> OrderResult:
        return cls(success=True, order=order)

    @classmethod
    def fail(cls, error: str) -> OrderResult:
        return cls(success=False, error=error)


@runtime_checkable
class SubscriptionHandle(Protocol):
    """Handle for an active market-data subscription.

    Returned by ``DataProvider.subscribe()``.  Used to unsubscribe
    or check subscription health.
    """

    @property
    def is_active(self) -> bool:
        """True while the subscription is live."""
        ...

    def unsubscribe(self) -> None:
        """Cancel the subscription."""
        ...


# Backward-compatible alias — old code imports ``Subscription``.
Subscription = SubscriptionHandle


@runtime_checkable
class DataProvider(Protocol):
    """Central data-access protocol.

    Replaces ``MarketDataPort``, ``MarketDataProvider``, and parts of
    ``BrokerGateway`` with a single, unified interface.

    Every analytics engine, API endpoint, CLI command, and replay/backtest
    engine obtains market data through this protocol.

    Implementations:
        - ``BrokerDataProvider`` — wraps a live broker connection
        - ``CsvDataProvider`` — CSV files for notebooks
        - ``ReplayDataProvider`` — historical replay
        - ``CacheDataProvider`` — adds TTL caching
        - ``CompositeDataProvider`` — fallback chain
        - ``DataFrameDataProvider`` — in-memory (tests)
    """

    @property
    def name(self) -> str:
        """Provider name for logging and registry lookup."""
        ...

    def get_quote(self, instrument_id: InstrumentId) -> QuoteSnapshot | None:
        """Get latest quote for an instrument."""
        ...

    def get_history(
        self,
        instrument_id: "InstrumentId",
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list["HistoricalBar"]:
        """Get historical OHLCV bars as a list of domain objects.

        Use :meth:`get_history_series` when you need the full
        ``HistoricalSeries`` with metadata.
        """
        ...

    def get_history_series(
        self,
        instrument_id: "InstrumentId",
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> "HistoricalSeries":
        """Get historical OHLCV bars as a normalized ``HistoricalSeries``.

        This is the first-class history object; the DataFrame returned by
        :meth:`get_history` is now just an export view of a ``HistoricalSeries``.
        """
        ...

    def get_depth(self, instrument_id: InstrumentId) -> MarketDepth | None:
        """Get market depth (order book)."""
        ...

    def get_option_chain(
        self,
        underlying: InstrumentId,
        *,
        expiry: date | None = None,
    ) -> OptionChain:
        """Get option chain for an underlying."""
        ...

    def get_future_chain(self, underlying: InstrumentId) -> FutureChain:
        """Get futures chain for an underlying."""
        ...

    def subscribe(
        self,
        instrument_id: InstrumentId,
        callback: Callable[[InstrumentId, QuoteSnapshot], None],
        *,
        depth: bool = False,
    ) -> SubscriptionHandle:
        """Subscribe to live market data."""
        ...

    def unsubscribe(self, subscription: SubscriptionHandle) -> None:
        """Cancel a subscription."""
        ...

    def history_batch(
        self,
        instrument_ids: list[InstrumentId],
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
    ) -> pd.DataFrame:
        """Load historical OHLCV for multiple instruments in one call."""
        ...

    def list_instruments(self, exchange: str | None = None) -> list[InstrumentId]:
        """List all known instruments, optionally filtered by exchange."""
        ...

    def get_quotes_batch(self, instrument_ids: list[InstrumentId]) -> list[QuoteSnapshot | None]:
        """Get latest quotes for multiple instruments in one call.
        
        Returns a list of quotes in the same order as instrument_ids.
        None for instruments where quote is unavailable.
        """
        ...


@runtime_checkable
class ExecutionProvider(Protocol):
    """Central execution-access protocol.

    Replaces scattered order placement across broker gateways.
    All order operations go through this interface.
    """

    @property
    def name(self) -> str:
        """Provider name for logging and registry lookup."""
        ...

    def place_order(self, request: OrderRequest) -> OrderResult:  # noqa: F811
        """Place an order."""
        ...

    def cancel_order(self, order_id: str) -> OrderResult:  # noqa: F811
        """Cancel an order by ID."""
        ...

    def modify_order(self, request: ModifyOrderRequest) -> OrderResult:  # noqa: F811
        """Modify an existing order."""
        ...

    def get_order_book(self) -> list[Order]:
        """Get all orders."""
        ...

    def get_positions(self) -> list[Position]:
        """Get current positions."""
        ...

    def get_holdings(self) -> list[Holding]:
        """Get current holdings."""
        ...

    def get_funds(self) -> Balance:
        """Get fund limits / balance."""
        ...
