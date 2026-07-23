"""PaperGateway — thin facade over PaperConnection."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from domain.commands import PlaceOrderCommand
from domain.entities import Account, Bar, Instrument, MarketDepth, Order, Position, Quote
from domain.enums import AssetClass, OrderStatus
from domain.ports.types import BrokerSnapshot
from domain.value_objects import InstrumentId, Money, OrderId, Price, TimeFrame
from plugins.brokers.common.capabilities import BrokerCapabilities
from plugins.brokers.common.extensions import BrokerExtensions
from plugins.brokers.paper.connection import PaperConnection

PAPER_CAPABILITIES = BrokerCapabilities(
    supports_market_order=True,
    supports_limit_order=True,
    supports_stop_order=False,
    supports_modify=True,
    supports_cancel=True,
    supported_asset_classes=frozenset({AssetClass.EQUITY}),
)


class PaperGateway:
    """Duck-typed BrokerAdapter surface; no network I/O."""

    def __init__(
        self,
        starting_cash: Money | None = None,
        auto_fill: bool = True,
    ) -> None:
        self.connection = PaperConnection(starting_cash=starting_cash, auto_fill=auto_fill)
        self.connection.connect()
        self.extensions = BrokerExtensions()

    def extension(self, ext_type: type) -> Any:
        """Look up a paper-specific capability by type."""
        return self.extensions.get(ext_type)

    def connect(self) -> None:
        """Connect to paper broker (delegates to connection)."""
        if self.connection.is_connected:
            return
        self.connection.connect()

    def close(self) -> None:
        self.connection.close()

    def get_quote(self, instrument_id: InstrumentId) -> Quote:
        return self.connection.market_data.get_quote(instrument_id)

    def set_quote(self, instrument_id: InstrumentId, bid: Decimal, ask: Decimal) -> None:
        self.connection.set_quote(instrument_id, bid, ask)

    def get_ltp(self, instrument_id: InstrumentId) -> Price:
        return self.connection.market_data.get_ltp(instrument_id)

    def ltp(self, instrument_id: InstrumentId) -> Price:
        """Alias for get_ltp() — matches Dhan/Upstox gateway API."""
        return self.get_ltp(instrument_id)

    def get_depth(self, instrument_id: InstrumentId) -> MarketDepth:
        return self.connection.market_data.get_depth(instrument_id)

    def depth(self, instrument_id: InstrumentId) -> MarketDepth:
        """Alias for get_depth() — matches Dhan/Upstox gateway API."""
        return self.get_depth(instrument_id)

    def get_history(
        self,
        instrument_id: InstrumentId,
        timeframe: TimeFrame,
        start: datetime,
        end: datetime,
    ) -> list[Bar]:
        return self.connection.market_data.get_history(instrument_id, timeframe, start, end)

    def history(
        self,
        instrument_id: InstrumentId,
        timeframe: TimeFrame,
        start: datetime,
        end: datetime,
    ) -> list[Bar]:
        """Alias for get_history() — matches Dhan/Upstox gateway API."""
        return self.get_history(instrument_id, timeframe, start, end)

    def place_order(self, command: PlaceOrderCommand) -> OrderId:
        return self.connection.orders_adapter.place_order(command)

    def submit_order(self, command: PlaceOrderCommand) -> OrderId:
        return self.place_order(command)

    def cancel_order(self, order_id: OrderId) -> None:
        self.connection.orders_adapter.cancel_order(order_id)

    def get_order(self, order_id: OrderId) -> Order:
        return self.connection.orders_adapter.get_order(order_id)

    def get_orderbook(self) -> list[Order]:
        return self.connection.orders_adapter.get_orderbook()

    def get_positions(self) -> list[Position]:
        return self.connection.portfolio.get_positions()

    def get_holdings(self) -> list[Position]:
        """Return positions held overnight (simplified: all positions for paper)."""
        return self.get_positions()

    def get_trade_book(self) -> list[Order]:
        """Return all filled orders as trade book."""
        return [o for o in self.connection.orders.values() if o.status == OrderStatus.FILLED]

    def get_funds(self) -> Account:
        return self.connection.portfolio.get_funds()

    def get_balance(self) -> Account:
        """Alias for get_funds() — matches Dhan/Upstox gateway API."""
        return self.get_funds()

    def authenticate(self) -> bool:
        """Paper broker is always authenticated."""
        return True

    def disconnect(self) -> None:
        """Disconnect paper broker."""
        self.close()

    def describe(self) -> dict[str, Any]:
        """Return broker metadata."""
        return {
            "broker": "paper",
            "name": "paper",
            "version": "1.0.0",
            "connected": self.connection.is_connected,
            "type": "simulated",
        }

    def load_instruments(self) -> None:
        """Paper broker has no external instrument source (noop)."""
        pass

    def search(self, query: str) -> list[Instrument]:
        """Search paper broker instruments by symbol."""
        return self.connection.instruments_adapter.search(query)

    def mass_status(self) -> BrokerSnapshot:
        return self.connection.mass_status()

    def capabilities(self) -> BrokerCapabilities:
        return PAPER_CAPABILITIES

    def modify_order(self, order_id: OrderId, command: PlaceOrderCommand) -> None:
        self.connection.orders_adapter.modify_order(order_id, command)
