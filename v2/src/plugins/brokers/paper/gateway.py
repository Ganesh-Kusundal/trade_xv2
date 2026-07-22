"""PaperGateway — thin facade over PaperConnection."""

from __future__ import annotations

from domain.commands import PlaceOrderCommand
from domain.entities import Account, Order, Position, Quote
from domain.enums import ExchangeId
from domain.value_objects import InstrumentId, Money, OrderId
from plugins.brokers.common.capabilities import BrokerCapabilities
from plugins.brokers.paper.connection import BrokerSnapshot, PaperConnection
from plugins.brokers.paper.wire import PaperWire

PAPER_CAPABILITIES = BrokerCapabilities(
    supports_market_orders=True,
    supports_limit_orders=True,
    supports_stop_orders=False,
    supports_modify=False,
    supports_websocket=False,
    supports_option_chain=False,
    supports_future_chain=False,
    max_orders_per_second=10_000,
    supported_exchanges=frozenset({ExchangeId.NSE, ExchangeId.BSE}),
)


class PaperGateway:
    """Duck-typed BrokerAdapter surface; no network I/O."""

    def __init__(
        self,
        starting_cash: Money | None = None,
        wire: PaperWire | None = None,
    ) -> None:
        self.connection = PaperConnection(starting_cash=starting_cash, wire=wire)

    def connect(self) -> None:
        self.connection.connect()

    def close(self) -> None:
        self.connection.close()

    def get_quote(self, instrument_id: InstrumentId) -> Quote:
        return self.connection.market_data.get_quote(instrument_id)

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

    def get_funds(self) -> Account:
        return self.connection.portfolio.get_funds()

    def mass_status(self) -> BrokerSnapshot:
        return self.connection.mass_status()

    def capabilities(self) -> BrokerCapabilities:
        return PAPER_CAPABILITIES

    def modify_order(self, order_id: OrderId, command: PlaceOrderCommand) -> None:
        raise NotImplementedError("paper broker does not support modify")
