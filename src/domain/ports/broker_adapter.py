"""BrokerAdapter — unified broker adapter abstract base class (composition root).

Phase 9.1 of the Instrument-Centric SDK Redesign.

This is the composition-root contract that unifies market-data access and
order execution behind a single interface.  A ``BrokerAdapter`` is a class
with ``broker_id``, ``is_connected``, ``authenticate()``, ``close()``, and
the union of :class:`DataProvider` and :class:`ExecutionProvider` methods.

Unlike structural Protocol conformance, this ABC enforces **nominal typing**
via ``@abstractmethod`` — any class that does not implement every required
method will fail at class instantiation time, not at call time.

For example::

    from domain.ports.broker_adapter import BrokerAdapter

    class MyBroker(BrokerAdapter):
        broker_id = "my_broker"
        @property
        def is_connected(self) -> bool: ...
        def authenticate(self) -> bool: ...
        def close(self) -> None: ...
        def quote(self, symbol, exchange) -> Quote: ...
        # ... all @abstractmethod must be implemented

Every concrete broker (``DhanWireAdapter``, ``UpstoxWireAdapter``,
``PaperGateway``) is now a nominal subclass of ``BrokerAdapter``.

Instrument loading & security mapping
-------------------------------------
Instrument master loading and symbol→broker-native-identifier mapping
(Dhan ``security_id``, Upstox ``instrument_key``, segment codes) are
**internal to each broker**. Gateways must only pass canonical
``(symbol, exchange)`` and receive canonical domain objects
(``Quote``, ``MarketDepth``, …). Wire identifiers must never leak into
gateway method signatures or return values.

Every broker implements :class:`brokers.common.instruments.BrokerInstrumentService`
behind its connection / broker facade:

* ``load_instruments()`` / ``load()`` — populate the in-memory resolver
* ``is_loaded()`` — gate subscriptions when the master is empty
* ``resolve_ref()`` — opaque wire ref consumed only by the connection

This is a pure domain port: it contains no broker-specific logic, no
implementation, and imports nothing from ``brokers.*`` or ``providers.*``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from domain.ports.protocols import DataProvider, ExecutionProvider

if TYPE_CHECKING:
    import pandas as pd

    from domain.entities import (
        Balance,
        Holding,
        MarketDepth,
        OptionChain,
        Order,
        OrderResponse,
        Position,
        Quote,
        Trade,
    )
    from domain.entities.options import FutureChain
    from brokers.common.broker_capabilities import BrokerCapabilities, CapabilityDescriptor
    from brokers.common.streaming import DepthStreamHandle


class BrokerAdapter(DataProvider, ExecutionProvider, ABC):
    """Unified broker interface: data + execution + lifecycle in one object.

    Nominal ABC — every concrete subclass must implement all ``@abstractmethod``
    methods. Instrument loading / security mapping is broker-internal (see
    module docstring). Callers use canonical symbols only.

    Methods are grouped into:
      1. Identity & lifecycle (broker_id, is_connected, authenticate, close)
      2. Market data (quote, ltp, depth, history, option_chain, future_chain, search)
      3. Order operations (place_order, cancel_order, modify_order, get_orderbook, get_trade_book)
      4. Portfolio (positions, holdings, funds)
      5. Streaming (stream, unstream, stream_depth, stream_order)
      6. Capability discovery (capabilities, list_capabilities, describe)
      7. Instrument management (load_instruments)
    """

    # ── Identity attributes ──────────────────────────────────────────────

    broker_id: str = ""
    is_connected: bool = False

    # ── Lifecycle ─────────────────────────────────────────────────────────

    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate against the broker; return True on success."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Tear down the connection and release resources."""
        ...

    # ── Market data ──────────────────────────────────────────────────────

    @abstractmethod
    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        """Get latest quote for a symbol."""
        ...

    @abstractmethod
    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        """Get last traded price for a symbol."""
        ...

    @abstractmethod
    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        """Get market depth (order book) for a symbol."""
        ...

    @abstractmethod
    def history(
        self,
        symbol: str | list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> Any:  # pd.DataFrame in practice
        """Get historical OHLCV data."""
        ...

    @abstractmethod
    def option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> OptionChain:
        """Get option chain for an underlying."""
        ...

    @abstractmethod
    def future_chain(self, underlying: str, exchange: str = "NFO") -> FutureChain:
        """Get futures chain for an underlying."""
        ...

    @abstractmethod
    def search(self, query: str) -> list[dict]:
        """Search for instruments by query string."""
        ...

    # ── Order operations ─────────────────────────────────────────────────

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        exchange: str = "NSE",
        side: str = "BUY",
        quantity: int = 1,
        price: Decimal = Decimal("0"),
        order_type: str = "MARKET",
        product_type: str = "INTRADAY",
        validity: str = "DAY",
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str | None = None,
        disclosed_quantity: int = 0,
        is_amo: bool = False,
    ) -> OrderResponse:
        """Place an order."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an order by ID."""
        ...

    @abstractmethod
    def modify_order(self, order_id: str, **changes: Any) -> OrderResponse:
        """Modify an existing order."""
        ...

    @abstractmethod
    def get_order(self, order_id: str) -> Order | None:
        """Fetch a single order by ID."""
        ...

    @abstractmethod
    def get_orderbook(self) -> list[Order]:
        """Get all open/recent orders."""
        ...

    @abstractmethod
    def get_trade_book(self) -> list[Trade]:
        """Get today's trades."""
        ...

    # ── Portfolio ─────────────────────────────────────────────────────────

    @abstractmethod
    def positions(self) -> list[Position]:
        """Get current positions."""
        ...

    @abstractmethod
    def holdings(self) -> list[Holding]:
        """Get current holdings."""
        ...

    @abstractmethod
    def funds(self) -> Balance:
        """Get fund limits / balance."""
        ...

    # ── Streaming ─────────────────────────────────────────────────────────

    @abstractmethod
    def stream(
        self,
        symbol: str,
        exchange: str = "NSE",
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any:
        """Subscribe to a live tick stream."""
        ...

    @abstractmethod
    def unstream(
        self,
        symbol: str,
        exchange: str = "NSE",
        on_tick: Any | None = None,
    ) -> None:
        """Unsubscribe from a live tick stream."""
        ...

    @abstractmethod
    def stream_depth(
        self,
        symbol: str,
        exchange: str = "NSE",
        *,
        levels: int = 5,
        on_depth: Any | None = None,
    ) -> Any:
        """Subscribe to depth (order book) streaming.

        ponytail: concrete adapters (Dhan, Upstox) accept ``levels`` as a
        positional keyword arg, not keyword-only.  Normalize in Phase 2.
        """
        ...

    @abstractmethod
    def stream_order(self, on_order: Any | None = None) -> Any:
        """Subscribe to order updates."""
        ...

    # ── Capability discovery ─────────────────────────────────────────────

    @abstractmethod
    def capabilities(self) -> BrokerCapabilities:
        """Return the capability matrix for this broker."""
        ...

    @abstractmethod
    def list_capabilities(self) -> CapabilityDescriptor:
        """Return capability descriptor (registry/router compatible)."""
        ...

    @abstractmethod
    def describe(self) -> dict:
        """Return broker metadata dict."""
        ...

    # ── Instrument management ─────────────────────────────────────────────

    @abstractmethod
    def load_instruments(self, source: str | None = None, use_cache: bool = True) -> None:
        """Load instruments into the broker-internal resolver."""
        ...

    # NOTE: ``trades()`` is intentionally NOT an abstract method. Every
    # concrete wire adapter inherits it from ``BaseWireAdapter``, which
    # delegates consistently to ``get_trade_book()``.
