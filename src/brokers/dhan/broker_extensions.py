"""Dhan extended capabilities — broker-specific methods beyond MarketDataGateway ABC.

This module composes four focused sub-facades and exposes them as direct
attributes. Callers should use the sub-facades directly rather than calling
methods through this class — the one-liner pass-throughs have been removed.

Usage::

    gateway = DhanBroker(connection)

    # Access sub-facades directly
    expiries = gateway.extended.data.get_option_expiries("NIFTY", "NFO")
    contracts = gateway.extended.data.get_futures_contracts("GOLD", "MCX")
    errors = gateway.extended.data.validate_order(symbol="RELIANCE", ...)
    super = gateway.extended.orders.place_super_order(...)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from brokers.dhan.account_capabilities import DhanAccountCapabilities
from brokers.dhan.data_capabilities import DhanDataCapabilities
from brokers.dhan.order_capabilities import DhanOrderCapabilities
from brokers.dhan.position_capabilities import DhanPositionCapabilities

if TYPE_CHECKING:
    from brokers.dhan.streaming.connection import DhanConnection

__all__ = [
    "DhanAccountCapabilities",
    "DhanDataCapabilities",
    "DhanExtendedCapabilities",
    "DhanOrderCapabilities",
    "DhanPositionCapabilities",
]


class DhanExtendedCapabilities:
    """Dhan-specific capabilities beyond the MarketDataGateway ABC.

    Composes four focused sub-facades:

    - :attr:`orders` — super/forever orders, conditional triggers
    - :attr:`account` — ledger, profile, IP, EDIS, TPIN
    - :attr:`data` — option chain, futures, expiries, alerts, validation
    - :attr:`positions` — positions, holdings, balance, exit, P&L exit
    """

    def __init__(self, conn: DhanConnection) -> None:
        self._conn = conn
        self.orders = DhanOrderCapabilities(conn)
        self.account = DhanAccountCapabilities(conn)
        self.data = DhanDataCapabilities(conn)
        self.positions = DhanPositionCapabilities(conn)

    @property
    def instruments(self) -> Any:
        """Dhan SymbolResolver (typed DhanInstrument lookups)."""
        return self._conn.instruments.resolver

    @property
    def identity(self) -> Any:
        """Access the Dhan identity provider (PR-A)."""
        return self._conn.identity
