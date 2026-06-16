"""Service Provider Interface (SPI) — fine-grained capability contracts.

These abstract classes define individual broker capabilities. Each port
represents one capability that a broker adapter can implement:

- ``OrderCommand`` — place/modify/cancel orders
- ``OrderQuery`` — query orders and trades
- ``MarketDataProvider`` — quotes, LTP, depth, historical data
- ``PortfolioProvider`` — positions, holdings, funds
- ``OptionsProvider`` — option chain data
- ``FuturesProvider`` — futures chain data
- ``MarginProvider`` — margin calculations
- ``BracketOrderProvider`` — bracket/cover orders
- ``GttOrderProvider`` — GTT (Good Till Triggered) orders
- ``SliceOrderCommand`` — order slicing
- ``ConditionalAlertProvider`` — conditional alerts
- ``MarketStatusProvider`` — market status
- ``NewsProvider`` — market news
- ``MarketIntelligencePort`` — market intelligence
- ``KillSwitchPort`` — emergency kill switch
- ``StaticIPPort`` — static IP management
- ``IdempotencyCachePort`` — idempotency caching

The ``MarketDataGateway`` ABC in ``brokers.common.gateway`` is a
coarse-grained facade that combines all these capabilities into a
single interface. Consumers typically use the gateway; broker
adapters implement the ports internally and wire them into the
gateway.

Relationship::

    MarketDataGateway (facade)
    ├── MarketDataProvider (quotes, ltp, depth)
    ├── OrderCommand (place, modify, cancel)
    ├── OrderQuery (get orders, trades)
    ├── PortfolioProvider (positions, holdings, funds)
    ├── OptionsProvider (option chain)
    ├── FuturesProvider (future chain)
    └── ... other ports
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import Any, Generic, Protocol, TypeVar

from brokers.common.core.domain import (
    ConditionalAlert,
    ConditionalAlertRequest,
    FundLimits,
    HistoricalCandle,
    Holding,
    MarketDepth,
    OptionContract,
    Order,
    OrderPreview,
    OrderRequest,
    OrderResponse,
    Position,
    Quote,
    SliceOrderRequest,
    Trade,
)


class InstrumentDefinition(Protocol):
    """Minimal instrument definition exposed by any broker resolver."""

    symbol: str
    canonical_symbol: str
    exchange_segment: Any
    security_id: str
    instrument_type: str
    underlying: str
    expiry: str | None
    strike: Decimal | None
    option_type: str
    lot_size: int
    tick_size: Decimal
    underlying_security_id: str


class OrderCommand(ABC):
    """Execute and manage orders. Gateway methods: place_order, cancel_order."""

    @abstractmethod
    def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place a new order."""
        ...

    @abstractmethod
    def modify_order(self, order_id: str, **changes: Any) -> dict[str, Any]:
        """Modify an existing open order."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order by ID."""
        ...

    @abstractmethod
    def preview_order(self, request: OrderRequest) -> OrderPreview:
        """Validate an order without submitting it."""
        ...


class OrderQuery(ABC):
    """Query orders and trades. Gateway methods: get_orderbook, get_trade_book, trades."""

    @abstractmethod
    def get_order(self, order_id: str) -> Order | None:
        """Fetch a single order by broker-assigned ID."""
        ...

    @abstractmethod
    def get_order_by_correlation_id(self, correlation_id: str) -> Order | None:
        """Fetch a single order by caller-supplied correlation ID."""
        ...

    @abstractmethod
    def get_order_list(self) -> list[Order]:
        """Fetch all orders for the day."""
        ...

    @abstractmethod
    def get_trades(self) -> list[Trade]:
        """Fetch the trade book."""
        ...

    @abstractmethod
    def get_trades_for_order(self, order_id: str) -> list[Trade]:
        """Fetch executed trades for a given order."""
        ...


class MarketDataProvider(ABC):
    """Market data queries. Gateway methods: quote, ltp, depth, history, option_chain."""

    @abstractmethod
    def get_quote(
        self,
        security_id: str,
        exchange_segment: Any,
        mode: str = "quote",
    ) -> Quote:
        """Return a ``Quote`` for a single security."""
        ...

    @abstractmethod
    def get_historical_daily(
        self,
        security_id: str,
        exchange_segment: Any,
        from_date: date,
        to_date: date,
        instrument: str = "EQUITY",
    ) -> list[HistoricalCandle]:
        """Return daily OHLCV candles."""
        ...

    @abstractmethod
    def get_historical_intraday(
        self,
        security_id: str,
        exchange_segment: Any,
        from_date: date,
        to_date: date,
        interval: str | None = None,
    ) -> list[HistoricalCandle]:
        """Return intraday OHLCV candles at the requested interval."""
        ...

    @abstractmethod
    def get_depth(self, security_id: str, exchange_segment: Any) -> MarketDepth:
        """Return order-book depth for an instrument."""
        ...

    @abstractmethod
    def get_option_chain(
        self,
        underlying: str,
        exchange_segment: Any,
        expiry: str,
    ) -> list[OptionContract]:
        """Return parsed option-chain contracts."""
        ...

    @abstractmethod
    def get_option_expiries(
        self,
        underlying: str,
        exchange_segment: Any,
    ) -> list[str]:
        """Return available expiry strings for the given underlying."""
        ...


class PortfolioProvider(ABC):
    """Portfolio data. Gateway methods: positions, holdings, funds."""

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """Return current positions for the day."""
        ...

    @abstractmethod
    def get_holdings(self) -> list[Holding]:
        """Return securities held in the demat account."""
        ...

    @abstractmethod
    def get_fund_limits(self) -> FundLimits:
        """Return account fund limits."""
        ...

    @abstractmethod
    def get_profile(self) -> dict[str, Any]:
        """Return the account profile."""
        ...

    @abstractmethod
    def get_ledger(self, from_date: date, to_date: date) -> list[dict[str, Any]]:
        """Return ledger entries between two dates."""
        ...


class OptionsProvider(ABC):
    """Option-chain aware provider. Gateway method: option_chain."""

    @abstractmethod
    def get_expiries(self, underlying: str, exchange_segment: Any) -> list[str]:
        """Return available option expiries."""
        ...

    @abstractmethod
    def get_option_chain(
        self,
        underlying: str,
        exchange_segment: Any,
        expiry: str,
    ) -> list[OptionContract]:
        """Return parsed option contracts."""
        ...


class MarginProvider(ABC):
    """Margin calculations. No direct gateway method; used internally by broker adapters."""

    @abstractmethod
    def calculate_margin(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Submit a margin-calculator request."""
        ...


class FuturesProvider(ABC):
    """Futures instrument capability. Gateway method: future_chain."""

    @abstractmethod
    def get_contracts(self, underlying: str, exchange_segment: Any) -> list[Any]:
        """Return futures contracts for an underlying symbol."""
        ...

    @abstractmethod
    def get_nearest_contract(self, underlying: str, exchange_segment: Any) -> Any:
        """Return the nearest active futures contract."""
        ...

    @abstractmethod
    def get_expiries(self, underlying: str, exchange_segment: Any) -> list[Any]:
        """Return futures contract expiries."""
        ...

    @abstractmethod
    def is_commodity(self, underlying: str) -> bool:
        """Return whether the underlying is a commodity."""
        ...


class BracketOrderProvider(ABC):
    """Bracket order capability. No direct gateway method; extends beyond the base gateway contract."""

    @abstractmethod
    def place_super_order(
        self,
        request: OrderRequest,
        target_price: Decimal,
        stop_loss_price: Decimal,
        trailing_jump: Decimal,
    ) -> Order:
        """Place a Dhan super/bracket order."""
        ...

    @abstractmethod
    def modify_super_order(
        self,
        order_id: str,
        leg_name: str,
        quantity: int,
        price: Decimal,
        trigger_price: Decimal,
    ) -> Order:
        """Modify a bracket/super order leg."""
        ...

    @abstractmethod
    def cancel_super_order(self, order_id: str, leg_name: str) -> bool:
        """Cancel a bracket/super order leg."""
        ...

    @abstractmethod
    def get_super_orders(self) -> list[Order]:
        """Return bracket/super orders."""
        ...


class CoverOrderProvider(ABC):
    """Cover order capability. No direct gateway method; extends beyond the base gateway contract."""

    @abstractmethod
    def place_cover_order(self, request: OrderRequest, stop_loss_price: Decimal) -> Order:
        """Place a cover order."""
        ...

    @abstractmethod
    def exit_cover_order(self, order_id: str) -> Order:
        """Exit a cover order."""
        ...


class GttOrderProvider(ABC):
    """Good-till-triggered order capability. No direct gateway method; extends beyond the base gateway contract."""

    @abstractmethod
    def place_forever_order(
        self,
        request: OrderRequest,
        order_flag: str,
        quantity2: int | None = None,
        price2: Decimal | None = None,
        trigger_price2: Decimal | None = None,
    ) -> Order:
        """Place a GTT/forever order."""
        ...

    @abstractmethod
    def modify_forever_order(
        self,
        order_id: str,
        order_flag: str,
        leg_name: str,
        quantity: int,
        price: Decimal,
        trigger_price: Decimal,
    ) -> Order:
        """Modify a GTT/forever order."""
        ...

    @abstractmethod
    def cancel_forever_order(self, order_id: str) -> bool:
        """Cancel a GTT/forever order."""
        ...

    @abstractmethod
    def get_forever_orders(self) -> list[Order]:
        """Return GTT/forever orders."""
        ...


class SliceOrderCommand(ABC):
    """Slice large orders into child orders. No direct gateway method; extends beyond the base gateway contract."""

    @abstractmethod
    def place_slice_order(self, request: SliceOrderRequest) -> list[Order]:
        """Split an order request into executable child orders."""
        ...


class ConditionalAlertProvider(ABC):
    """Conditional alert capability. No direct gateway method; extends beyond the base gateway contract."""

    @abstractmethod
    def place_alert(self, request: ConditionalAlertRequest) -> str:
        """Place a conditional alert and return its ID."""
        ...

    @abstractmethod
    def get_alert(self, alert_id: str) -> ConditionalAlert:
        """Fetch a conditional alert."""
        ...

    @abstractmethod
    def list_alerts(self) -> list[ConditionalAlert]:
        """List conditional alerts."""
        ...

    @abstractmethod
    def delete_alert(self, alert_id: str) -> bool:
        """Delete a conditional alert."""
        ...


class MarketStatusProvider(ABC):
    """Market/session status provider. No direct gateway method; extends beyond the base gateway contract."""

    @abstractmethod
    def get_market_status(self) -> dict[str, Any]:
        """Return market/session status."""
        ...


class NewsProvider(ABC):
    """News feed provider. No direct gateway method; extends beyond the base gateway contract."""

    @abstractmethod
    def get_news(self, **filters: Any) -> list[Any]:
        """Return news items matching optional filters."""
        ...


T = TypeVar("T")


class IdempotencyCachePort(ABC, Generic[T]):
    """Idempotency cache for order placement safety. Infrastructure port; not exposed via gateway."""

    @abstractmethod
    def get(self, key: str) -> T | None:
        """Return a cached response for an idempotency key."""
        ...

    @abstractmethod
    def put(self, key: str, value: T) -> None:
        """Store a response for an idempotency key."""
        ...


class MarketIntelligencePort(ABC):
    """Aggregated market intelligence — PCR, Max Pain, OI, FII/DII, Smartlist."""

    @abstractmethod
    def get_pcr(
        self,
        instrument_key: str,
        expiry: str,
        date: str,
        bucket_interval: int = 1,
    ) -> dict[str, Any]:
        """Return Put/Call ratio data."""
        ...

    @abstractmethod
    def get_max_pain(
        self,
        instrument_key: str,
        expiry: str,
        date: str,
        bucket_interval: int = 1,
    ) -> dict[str, Any]:
        """Return max-pain analysis."""
        ...

    @abstractmethod
    def get_oi(self, instrument_key: str, expiry: str, date: str) -> dict[str, Any]:
        """Return open-interest build-up."""
        ...

    @abstractmethod
    def get_fii_flow(
        self, data_type: str = "NSE_FO|INDEX_FUTURES", interval: str = "1D"
    ) -> dict[str, Any]:
        """Return FII/DII flow."""
        ...

    @abstractmethod
    def get_dii_flow(self, interval: str = "1D") -> dict[str, Any]:
        """Return DII flow."""
        ...

    @abstractmethod
    def get_smartlist(
        self,
        kind: str,
        asset_type: str = "INDEX",
        category: str = "TOP_TRADED",
    ) -> dict[str, Any]:
        """Return the broker's curated symbol list."""
        ...


class KillSwitchPort(ABC):
    """User-level kill switch."""

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        """Return current kill-switch state."""
        ...

    @abstractmethod
    def set_status(self, updates: list[dict[str, str]]) -> dict[str, Any]:
        """Toggle kill switches per segment."""
        ...


class StaticIPPort(ABC):
    """Static IP configuration."""

    @abstractmethod
    def get_static_ip(self) -> dict[str, str]:
        """Return the currently registered static IP(s)."""
        ...

    @abstractmethod
    def set_static_ip(self, primary: str, secondary: str | None = None) -> dict[str, str]:
        """Register a new primary (and optional secondary) static IP."""
        ...
