"""DhanGateway — BrokerAdapter facade over DhanConnection."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from domain.commands import PlaceOrderCommand
from domain.entities import Account, Bar, Instrument, MarketDepth, Order, Position, Quote
from domain.enums import ExchangeId
from domain.value_objects import InstrumentId, OrderId, Price, TimeFrame
from plugins.brokers.common.capabilities import BrokerCapabilities
from plugins.brokers.common.transport import BaseTransport
from plugins.brokers.dhan.auth import DhanTokenManager
from plugins.brokers.dhan.config import DhanConfig
from plugins.brokers.dhan.connection import DhanConnection


class DhanGateway:
    def __init__(
        self,
        config: DhanConfig | None = None,
        transport: BaseTransport | None = None,
        token_manager: DhanTokenManager | None = None,
    ) -> None:
        self.connection = DhanConnection(
            config=config,
            transport=transport,
            token_manager=token_manager,
        )

    def connect(self) -> None:
        self.connection.connect()

    def authenticate(self) -> bool:
        return self.connection.authenticate()

    def close(self) -> None:
        self.connection.disconnect()

    def disconnect(self) -> None:
        self.close()

    def get_quote(self, instrument_id: InstrumentId) -> Quote:
        return self.connection.market_data.get_quote(instrument_id)

    def ltp(self, instrument_id: InstrumentId) -> Price:
        return self.connection.market_data.get_ltp(instrument_id)

    def depth(self, instrument_id: InstrumentId) -> MarketDepth:
        return self.connection.market_data.get_depth(instrument_id)

    def history(
        self,
        instrument_id: InstrumentId,
        timeframe: TimeFrame,
        start: datetime,
        end: datetime,
    ) -> list[Bar]:
        return self.connection.market_data.get_history(instrument_id, timeframe, start, end)

    def place_order(self, command: PlaceOrderCommand) -> OrderId:
        return self.connection.orders.place_order(command)

    def submit_order(self, command: PlaceOrderCommand) -> OrderId:
        return self.place_order(command)

    def cancel_order(self, order_id: OrderId) -> None:
        self.connection.orders.cancel_order(order_id)

    def modify_order(self, order_id: OrderId, command: PlaceOrderCommand) -> None:
        self.connection.orders.modify_order(order_id, command)

    def get_order(self, order_id: OrderId) -> Order:
        return self.connection.orders.get_order(order_id)

    def get_orderbook(self) -> list[Order]:
        return self.connection.orders.get_orderbook()

    def get_positions(self) -> list[Position]:
        return self.connection.portfolio.get_positions()

    def get_holdings(self) -> list[Position]:
        return self.connection.portfolio.get_holdings()

    def get_funds(self) -> Account:
        return self.connection.portfolio.get_funds()

    def get_balance(self) -> Account:
        return self.get_funds()

    def load_instruments(self) -> None:
        self.connection.load_instruments()

    def search(self, query: str) -> list[Instrument]:
        return self.connection.instruments.search(query)

    def stream(
        self,
        instrument_id: InstrumentId,
        on_quote: Callable[[Quote], None] | None = None,
    ) -> None:
        self.connection.streaming.stream(instrument_id, on_quote)

    def unstream(self, instrument_id: InstrumentId) -> None:
        self.connection.streaming.unstream(instrument_id)

    def stream_order(self, on_order: Callable[[Order], None] | None = None) -> None:
        self.connection.streaming.stream_order(on_order)

    def mass_status(self) -> dict[str, Any]:
        return self.connection.mass_status()

    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(
            supports_market_orders=True,
            supports_limit_orders=True,
            supports_stop_orders=True,
            supports_modify=True,
            supports_websocket=True,
            supports_option_chain=True,
            supports_future_chain=True,
            max_orders_per_second=10,
            supported_exchanges=frozenset({ExchangeId.NSE, ExchangeId.BSE}),
        )
