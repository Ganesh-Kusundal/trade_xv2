"""MockBroker — thin legacy wrapper for backward compatibility."""

from __future__ import annotations

import random
from decimal import Decimal

from brokers.common.core.domain import Balance, Holding, OrderResponse, Position
from brokers.common.oms.context import TradingContext

from .paper_gateway import PaperGateway


class MockBroker:
    """Thin backward-compatibility wrapper around PaperGateway.

    Exposes a ``connect()`` / ``disconnect()`` lifecycle that earlier code
    expected, while delegating everything else to a PaperGateway.
    """

    def __init__(
        self,
        initial_capital: Decimal = Decimal("1000000"),
        name: str = "paper",
        trading_context: TradingContext | None = None,
    ) -> None:
        self._name = name
        self._id = f"paper-{random.randint(1000, 9999)}"
        self._connected = False
        self._gw = PaperGateway(
            initial_capital=initial_capital,
            trading_context=trading_context,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def broker_id(self) -> str:
        return self._id

    @property
    def gateway(self) -> PaperGateway:
        return self._gw

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> bool:
        self._connected = False
        return True

    def is_connected(self) -> bool:
        return self._connected

    def get_quote(self, symbol: str, exchange: str = "NSE") -> dict:
        return self._gw.quote(symbol, exchange)

    def place_order(self, *args, **kwargs) -> OrderResponse:
        return self._gw.place_order(*args, **kwargs)

    def cancel_order(self, order_id: str) -> bool:
        return self._gw.cancel_order(order_id)

    def get_orderbook(self) -> list[dict]:
        return self._gw.get_orderbook()

    def get_trade_book(self) -> list[dict]:
        return self._gw.get_trade_book()

    def get_positions(self) -> list[Position]:
        return self._gw.positions()

    def get_holdings(self) -> list[Holding]:
        return self._gw.holdings()

    def get_balance(self) -> Balance:
        return self._gw.funds()


# Backward-compatibility alias
PaperBroker = MockBroker
