"""BrokerSession — composition root for the new Instrument-centric API.

This is the new entry point for creating instruments with providers injected.
It wraps the existing MarketDataGateway and creates DataProvider/ExecutionProvider
instances that satisfy the domain protocols.

Usage:
    session = BrokerSession(gateway)
    stock = session.stock("RELIANCE")
    stock.ltp  # Fetches quote via provider
    stock.buy(10, price=2450)  # Places order via execution provider
"""

from __future__ import annotations

import threading
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

    def __repr__(self) -> str:
        return f"BrokerSession(broker={self._broker_id}, gateway={type(self._gw).__name__})"
