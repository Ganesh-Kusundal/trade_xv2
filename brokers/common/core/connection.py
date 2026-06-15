"""DEPRECATED: BrokerConnection + Capability enum. Kept for Upstox backward compatibility only.

New broker adapters should use broker-specific gateway patterns:
- Dhan: brokers.dhan.gateway.BrokerGateway + brokers.dhan.connection.DhanConnection
- Paper: brokers.paper.PaperGateway
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class Capability(str, Enum):
    """Capabilities a broker connection can provide.

    Used for runtime capability discovery (like Trade_J's capability pattern).
    """

    MARKET_DATA = "market_data"
    ORDER_COMMAND = "order_command"
    ORDER_QUERY = "order_query"
    PORTFOLIO = "portfolio"
    OPTIONS_CHAIN = "options_chain"
    INSTRUMENTS = "instruments"
    FUTURES = "futures"
    HISTORICAL_DATA = "historical_data"
    WEBSOCKET = "websocket"
    BRACKET_ORDER = "bracket_order"
    COVER_ORDER = "cover_order"
    GTT_ORDER = "gtt_order"
    SLICE_ORDER = "slice_order"
    MARGIN = "margin"
    NEWS = "news"
    SESSION_RISK = "session_risk"
    ALERTS = "alerts"
    MARKET_STATUS = "market_status"
    DEPTH = "depth"
    ORDER_STREAM = "order_stream"
    IDEMPOTENCY = "idempotency"
    MULTI_ORDER = "multi_order"
    KILL_SWITCH = "kill_switch"
    STATIC_IP = "static_ip"
    SMARTLIST = "smartlist"
    FII_DII = "fii_dii"
    OI_PCR_MAXPAIN = "oi_pcr_maxpain"
    MARKET_INTELLIGENCE = "market_intelligence"
    FUNDAMENTALS = "fundamentals"
    IPO = "ipo"
    MUTUAL_FUNDS = "mutual_funds"
    PAYMENTS = "payments"
    INSTRUMENT_SEARCH = "instrument_search"
    HISTORICAL_TRADES = "historical_trades"
    TSL = "trailing_stop_loss"
    MTF = "mtf"
    WEBHOOKS = "webhooks"
    PORTFOLIO_STREAM = "portfolio_stream"
    ORDER_SLICING = "order_slicing"
    DEPTH_30 = "depth_30"
    LEVEL2_MARKET_DATA = "level2_market_data"
    OPTION_GREEKS = "option_greeks"
    GLOBAL_MARKETS = "global_markets"
    VOLATILITY_INDEX = "volatility_index"


class ConnectionStatus(str, Enum):
    """Lifecycle status of a broker connection."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"

    def is_connected(self) -> bool:
        return self == ConnectionStatus.CONNECTED


class BrokerConnection(ABC):
    """Abstract broker connection with capability-based service discovery.

    Subclasses register providers in ``_capability_map`` during init.
    Consumers discover services at runtime::

        conn = SomeBrokerConnection(...)
        if conn.has_capability(Capability.MARKET_DATA):
            md_provider = conn.get_capability(Capability.MARKET_DATA)
            quote = md_provider.get_quote("2885")
    """

    def __init__(
        self,
        name: str,
        broker_id: str,
        capabilities: set[Capability] | None = None,
    ):
        self._name = name
        self._broker_id = broker_id
        self._capabilities: set[Capability] = capabilities or set()
        self._capability_map: dict[Capability, Any] = {}
        self._status: ConnectionStatus = ConnectionStatus.DISCONNECTED

    # ── Abstract methods ─────────────────────────────────────────

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to the broker."""
        ...

    @abstractmethod
    def disconnect(self) -> bool:
        """Tear down the broker connection."""
        ...

    @abstractmethod
    def reconnect(self) -> bool:
        """Re-establish a dropped connection."""
        ...

    # ── Properties ───────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self._name

    @property
    def broker_id(self) -> str:
        return self._broker_id

    @property
    def status(self) -> ConnectionStatus:
        return self._status

    # ── Capability discovery (Trade_J pattern) ────────────────────

    def capabilities(self) -> set[Capability]:
        """Return the set of capabilities this connection supports."""
        return set(self._capabilities)

    def has_capability(self, capability: Capability) -> bool:
        """Check if this connection supports a given capability."""
        return capability in self._capabilities

    def get_capability(self, capability: Capability):
        """Get the provider implementation for a capability.

        Returns ``None`` if the capability is not supported.
        """
        return self._capability_map.get(capability)

    # ── Internal helpers for subclasses ───────────────────────────

    def _register_capability(self, capability: Capability, provider: Any) -> None:
        """Register a provider implementation for a capability."""
        self._capabilities.add(capability)
        self._capability_map[capability] = provider

    def _set_status(self, status: ConnectionStatus) -> None:
        """Update connection status."""
        self._status = status

    # ── Context Manager ─────────────────────────────────────────

    def __enter__(self) -> BrokerConnection:
        """Context manager support — auto-connects on entry."""
        self.connect()
        return self

    def __exit__(self, *args) -> None:
        """Context manager support — auto-disconnects on exit."""
        self.disconnect()
