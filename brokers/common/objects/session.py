"""BrokerSession — composition root for the new Instrument-centric API.

This is the new entry point for creating instruments with providers injected.
It wraps the existing MarketDataGateway and creates DataProvider/ExecutionProvider
instances that satisfy the domain protocols.

Usage:
    session = BrokerSession(gateway)
    stock = session.stock("RELIANCE")
    stock.ltp  # Fetches quote via provider
    session.buy(stock, 10, price=2450)  # Places order via execution provider
"""

from __future__ import annotations

import threading
from decimal import Decimal
from typing import Any

from domain.instruments.instrument import Equity, Future, Index
from domain.options.option_chain import OptionChain

from brokers.common.adapter_factory import (
    create_data_adapter,
    create_execution_provider,
)


class BrokerSession:
    """Composition root for instrument creation with provider injection."""

    def __init__(self, gateway: Any, *, broker_id: str = "dhan") -> None:
        self._gw = gateway
        self._broker_id = broker_id
        self._data_provider = None
        self._execution_provider = None
        self._lock = threading.Lock()

    def _get_data_provider(self):
        """Lazy-create the data provider adapter (thread-safe)."""
        if self._data_provider is None:
            with self._lock:
                if self._data_provider is None:
                    self._data_provider = create_data_adapter(
                        self._gw, broker_id=self._broker_id
                    )
        return self._data_provider

    def _get_execution_provider(self):
        """Lazy-create the execution provider adapter (thread-safe).

        Resolves via the adapter factory, so broker-specific construction
        stays out of this class — no ``if broker == ...`` branching. Returns
        ``None`` for brokers without an execution provider.
        """
        if self._execution_provider is None:
            with self._lock:
                if self._execution_provider is None:
                    self._execution_provider = create_execution_provider(
                        self._gw, broker_id=self._broker_id
                    )
        return self._execution_provider

    def stock(self, symbol: str, exchange: str = "NSE") -> Equity:
        """Create an Equity instrument with providers injected."""
        return Equity(
            symbol,
            exchange=exchange,
            data_provider=self._get_data_provider(),
            execution_provider=self._get_execution_provider(),
        )

    def index(self, name: str, exchange: str = "NSE") -> Index:
        """Create an Index instrument with providers injected."""
        return Index(
            name,
            exchange=exchange,
            data_provider=self._get_data_provider(),
        )

    def future(self, symbol: str, expiry: Any, exchange: str = "NFO") -> Future:
        """Create a Future instrument with providers injected."""
        return Future(
            symbol,
            exchange=exchange,
            expiry=expiry,
            data_provider=self._get_data_provider(),
        )

    def option_chain(self, underlying: str, expiry: Any = None, exchange: str = "NSE") -> OptionChain:
        """Fetch option chain for an underlying."""
        instrument = self.index(underlying, exchange=exchange)
        return instrument.option_chain(expiry=expiry)

    # ── Execution (order placement lives here, not on Instrument) ──────

    def _place_order(
        self,
        instrument: "Equity | Index | Future",
        side: str,
        quantity: int,
        price: Decimal | None = None,
        order_type: str = "LIMIT",
        product_type: str = "INTRADAY",
        trigger_price: Decimal | None = None,
    ):
        """Place an order (internal helper). Delegates to execution_provider."""
        executor = self._get_execution_provider()
        if executor is None:
            raise RuntimeError("No execution provider configured for this broker")
        from domain.orders.requests import OrderRequest

        return executor.place_order(
            OrderRequest(
                symbol=instrument.symbol,
                exchange=instrument.exchange,
                transaction_type=side,
                quantity=quantity,
                price=price or Decimal("0"),
                order_type=order_type,
                product_type=product_type,
                trigger_price=trigger_price,
            )
        )

    def buy(
        self,
        instrument: "Equity | Index | Future",
        quantity: int,
        price: Decimal | None = None,
        order_type: str = "LIMIT",
        product_type: str = "INTRADAY",
    ):
        """Place a buy order for the given instrument."""
        return self._place_order(
            instrument, "BUY", quantity, price, order_type, product_type
        )

    def sell(
        self,
        instrument: "Equity | Index | Future",
        quantity: int,
        price: Decimal | None = None,
        order_type: str = "LIMIT",
        product_type: str = "INTRADAY",
    ):
        """Place a sell order for the given instrument."""
        return self._place_order(
            instrument, "SELL", quantity, price, order_type, product_type
        )

    def market(
        self,
        instrument: "Equity | Index | Future",
        quantity: int,
        side: str = "BUY",
    ):
        """Place a market order for the given instrument."""
        if side not in ("BUY", "SELL"):
            raise ValueError(f"Invalid side: {side!r}. Must be 'BUY' or 'SELL'.")
        return self._place_order(instrument, side, quantity, order_type="MARKET")

    def limit(
        self,
        instrument: "Equity | Index | Future",
        quantity: int,
        price: Decimal,
        side: str = "BUY",
    ):
        """Place a limit order for the given instrument."""
        if side not in ("BUY", "SELL"):
            raise ValueError(f"Invalid side: {side!r}. Must be 'BUY' or 'SELL'.")
        return self._place_order(instrument, side, quantity, price=price)

    def stop_loss(
        self,
        instrument: "Equity | Index | Future",
        quantity: int,
        trigger_price: Decimal,
        side: str = "BUY",
    ):
        """Place a stop-loss order for the given instrument."""
        if side not in ("BUY", "SELL"):
            raise ValueError(f"Invalid side: {side!r}. Must be 'BUY' or 'SELL'.")
        return self._place_order(
            instrument, side.upper(), quantity,
            order_type="STOP_LOSS_MARKET", trigger_price=trigger_price,
        )

    def __repr__(self) -> str:
        return f"BrokerSession(broker={self._broker_id}, gateway={type(self._gw).__name__})"
