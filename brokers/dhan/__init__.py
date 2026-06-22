"""DhanHQ broker adapter package — clean architecture.

Canonical domain types (Order, Position, Holding, Trade, Side, OrderStatus,
OrderType, ProductType, Validity, FundLimits) are no longer re-exported here.
Import them from ``brokers.common.core.domain`` instead::

    from brokers.common.core.domain import Order, Side, OrderStatus
    from brokers.dhan import Exchange, Instrument, BrokerGateway
"""

# ── Dhan-specific domain types ──────────────────────────────────────────────
from brokers.dhan.connection import DhanConnection
from brokers.common.core.domain import Balance, DepthLevel, MarketDepth, Quote
from brokers.dhan.domain import (
    Exchange,
    Instrument,
    InstrumentType,
    OptionType,
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
from brokers.dhan.factory import BrokerFactory
from brokers.dhan.gateway import BrokerGateway
from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.identity import (
    DHAN_SEGMENTS,
    DhanIdentityError,
    DhanIdentityProvider,
    DhanIdentitySource,
    DhanInstrumentRef,
    coerce_identity_provider,
    is_dhan_segment,
)
from brokers.dhan.loader import InstrumentLoader
from brokers.dhan.reconciliation import DhanReconciliationService, ReconciliationReport

# ── Infrastructure ──────────────────────────────────────────────────────────
from brokers.dhan.resolver import SymbolResolver
from brokers.dhan.websocket import DhanMarketFeed, DhanOrderStream, PollingMarketFeed

__all__ = [
    # Exceptions
    "AuthenticationError",
    # Domain — Dhan-specific types
    "Balance",
    "BrokerFactory",
    "BrokerGateway",
    "ConfigurationError",
    "DepthLevel",
    "DHAN_SEGMENTS",
    "DhanConnection",
    "DhanError",
    "DhanHttpClient",
    # Identity provider (PR-A)
    "DhanIdentityError",
    "DhanIdentityProvider",
    "DhanIdentitySource",
    "DhanInstrumentRef",
    "coerce_identity_provider",
    "is_dhan_segment",
    # WebSocket
    "DhanMarketFeed",
    "DhanOrderStream",
    # Reconciliation
    "DhanReconciliationService",
    "Exchange",
    "Instrument",
    "InstrumentLoader",
    "InstrumentNotFoundError",
    "InstrumentType",
    "MarketDataError",
    "MarketDepth",
    "OptionType",
    "OrderError",
    "PollingMarketFeed",
    "Quote",
    "RateLimitError",
    "ReconciliationReport",
    # Infrastructure
    "SymbolResolver",
]
