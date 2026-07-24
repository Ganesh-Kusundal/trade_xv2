"""PaperConnection — owns in-memory orders, positions, quotes, cash."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from domain.entities import Instrument, Order, Position, Quote
from domain.ports.types import BrokerSnapshot
from domain.value_objects import AccountId, InstrumentId, Money, Price, Quantity
from plugins.brokers.common.constants import DEFAULT_CURRENCY, PAPER_STARTING_CASH
from plugins.brokers.common.liveness import ConnectionLiveness
from plugins.brokers.paper.adapters.instruments import PaperInstrumentsAdapter
from plugins.brokers.paper.adapters.market_data import PaperMarketDataAdapter
from plugins.brokers.paper.adapters.orders import PaperOrdersAdapter
from plugins.brokers.paper.adapters.portfolio import PaperPortfolioAdapter
from plugins.brokers.paper.adapters.streaming import PaperStreamingAdapter


class PaperConnection(ConnectionLiveness):
    def __init__(
        self,
        starting_cash: Money | None = None,
        auto_fill: bool = True,
    ) -> None:
        currency = starting_cash.currency if starting_cash else DEFAULT_CURRENCY
        self.cash = starting_cash or Money(amount=PAPER_STARTING_CASH, currency=currency)
        self.quotes: dict[InstrumentId, object] = {}
        self.orders: dict[str, Order] = {}
        self.positions: dict[InstrumentId, Position] = {}
        self.instruments: dict[InstrumentId, Instrument] = {}
        self.auto_fill = auto_fill
        self._connected = False

        self.orders_adapter = PaperOrdersAdapter(self)
        self.market_data = PaperMarketDataAdapter(self)
        self.portfolio = PaperPortfolioAdapter(self)
        self.instruments_adapter = PaperInstrumentsAdapter(self)
        self.streaming = PaperStreamingAdapter(self)

    def _transport_connected(self) -> bool:
        """Paper has no auth concept — connected is the whole liveness contract."""
        return self._connected

    def connect(self) -> None:
        self._connected = True

    def close(self) -> None:
        self._connected = False

    def set_quote(self, instrument_id: InstrumentId, bid: Decimal, ask: Decimal) -> None:
        self.quotes[instrument_id] = Quote(
            instrument_id=instrument_id,
            bid=Price(value=bid),
            ask=Price(value=ask),
            bid_size=Quantity(value=Decimal("100")),
            ask_size=Quantity(value=Decimal("100")),
            timestamp=datetime.now(),
        )

    def require_connected(self) -> None:
        if not self._connected:
            raise RuntimeError("paper broker not connected")

    def mass_status(self) -> BrokerSnapshot:
        return BrokerSnapshot(
            orders=list(self.orders.values()),
            positions=list(self.positions.values()),
            account=self.portfolio.get_funds(),
        )

    def account_id(self) -> AccountId:
        return AccountId(value="paper")
