"""DhanHQ broker adapter package — clean architecture.

Canonical domain types (Order, Position, Holding, Trade, Side, OrderStatus,
OrderType, ProductType, Validity, FundLimits) are no longer re-exported here.
Import them from ``brokers.common.core.domain`` instead::

    from brokers.common.core.domain import Order, Side, OrderStatus
    from brokers.dhan import Exchange, Instrument, BrokerGateway
"""

# ── Dhan-specific domain types ──────────────────────────────────────────────
from brokers.dhan.domain import (
    Balance,
    DepthLevel,
    Exchange,
    Instrument,
    InstrumentType,
    MarketDepth,
    OptionType,
    Quote,
)
# ── Exceptions ──────────────────────────────────────────────────────────────
from brokers.dhan.exceptions import (
    AuthenticationError,
    ConfigurationError,
    DhanError,
    InstrumentNotFoundError,
    MarketDataError,
    OrderError,
    RateLimitError,
)
# ── Infrastructure ──────────────────────────────────────────────────────────
from brokers.dhan.resolver import SymbolResolver
from brokers.dhan.loader import InstrumentLoader
from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.connection import DhanConnection
from brokers.dhan.gateway import BrokerGateway
from brokers.dhan.factory import BrokerFactory
from brokers.dhan.websocket import DhanMarketFeed, DhanOrderStream, PollingMarketFeed
from brokers.dhan.reconciliation import DhanReconciliationService, ReconciliationReport

__all__ = [
    # Domain — Dhan-specific types
    "Balance", "DepthLevel", "Exchange", "Instrument", "InstrumentType",
    "MarketDepth", "OptionType", "Quote",
    # Exceptions
    "AuthenticationError", "ConfigurationError", "DhanError", "InstrumentNotFoundError",
    "MarketDataError", "OrderError", "RateLimitError",
    # Infrastructure
    "SymbolResolver", "InstrumentLoader", "DhanHttpClient",
    "DhanConnection", "BrokerGateway", "BrokerFactory",
    # WebSocket
    "DhanMarketFeed", "DhanOrderStream", "PollingMarketFeed",
    # Reconciliation
    "DhanReconciliationService", "ReconciliationReport",
]
