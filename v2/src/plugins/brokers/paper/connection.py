"""PaperConnection — owns in-memory orders, positions, quotes, cash."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from domain.entities import Account, Instrument, Order, Position, Quote
from domain.value_objects import AccountId, InstrumentId, Money
from plugins.brokers.paper.adapters.instruments import PaperInstrumentsAdapter
from plugins.brokers.paper.adapters.market_data import PaperMarketDataAdapter
from plugins.brokers.paper.adapters.orders import PaperOrdersAdapter
from plugins.brokers.paper.adapters.portfolio import PaperPortfolioAdapter
from plugins.brokers.paper.adapters.streaming import PaperStreamingAdapter
from plugins.brokers.paper.wire import PaperWire


@dataclass(frozen=True, slots=True)
class BrokerSnapshot:
    orders: tuple[Order, ...]
    positions: tuple[Position, ...]
    account: Account


class PaperConnection:
    def __init__(
        self,
        starting_cash: Money | None = None,
        wire: PaperWire | None = None,
    ) -> None:
        self.wire = wire or PaperWire()
        currency = starting_cash.currency if starting_cash else "INR"
        self.cash = starting_cash or Money(amount=Decimal("1_000_000"), currency=currency)
        self.quotes: dict[InstrumentId, Quote] = {}
        self.orders: dict[str, Order] = {}
        self.positions: dict[InstrumentId, Position] = {}
        self.instruments: dict[InstrumentId, Instrument] = {}
        self._connected = False

        self.orders_adapter = PaperOrdersAdapter(self)
        self.market_data = PaperMarketDataAdapter(self)
        self.portfolio = PaperPortfolioAdapter(self)
        self.instruments_adapter = PaperInstrumentsAdapter(self)
        self.streaming = PaperStreamingAdapter(self)

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        self._connected = True

    def close(self) -> None:
        self._connected = False

    def set_quote(self, quote: Quote) -> None:
        self.quotes[quote.instrument_id] = quote

    def require_connected(self) -> None:
        if not self._connected:
            raise RuntimeError("paper broker not connected")

    def mass_status(self) -> BrokerSnapshot:
        return BrokerSnapshot(
            orders=tuple(self.orders.values()),
            positions=tuple(self.positions.values()),
            account=self.portfolio.get_funds(),
        )

    def account_id(self) -> AccountId:
        return AccountId(value="paper")
