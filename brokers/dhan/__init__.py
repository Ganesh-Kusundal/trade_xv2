"""DhanHQ broker adapter package — clean architecture.

Canonical domain types (Order, Position, Holding, Trade, Side, OrderStatus,
OrderType, ProductType, Validity, FundLimits) live in ``domain``::

    from domain import Order, Side, OrderStatus
    from brokers.dhan import Exchange, DhanInstrument, DhanBrokerGateway
"""

# ── Dhan-specific domain types ──────────────────────────────────────────────
from brokers.dhan.connection import DhanConnection
from brokers.dhan.domain import (
    Exchange,
    DhanInstrument,
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
from brokers.dhan.gateway import DhanBrokerGateway
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
from domain import Balance, DepthLevel, MarketDepth, Quote

__all__ = [
    "DHAN_SEGMENTS",
    # Exceptions
    "AuthenticationError",
    # Domain — Dhan-specific types
    "Balance",
    "BrokerFactory",
    "DhanBrokerGateway",
    "ConfigurationError",
    "DepthLevel",
    "DhanConnection",
    "DhanError",
    "DhanHttpClient",
    # Identity provider (PR-A)
    "DhanIdentityError",
    "DhanIdentityProvider",
    "DhanIdentitySource",
    "DhanInstrumentRef",
    # WebSocket
    "DhanMarketFeed",
    "DhanOrderStream",
    # Reconciliation
    "DhanReconciliationService",
    "Exchange",
    "DhanInstrument",
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
    "coerce_identity_provider",
    "is_dhan_segment",
]

# ── Extension + data/execution self-registration (ADR-007) ────────────────
from tradex.runtime.adapter_factory import (
    register_broker_extensions,
    register_data_adapter,
    register_execution_provider,
)
from brokers.dhan.data_provider import DhanDataProvider
from brokers.dhan.extensions.depth20 import DhanDepth20Extension
from brokers.dhan.extensions.depth200 import DhanDepth200Extension
from brokers.dhan.extensions.forever_order import DhanForeverOrderExtension
from brokers.dhan.extensions.super_order import DhanSuperOrderExtension
from brokers.dhan.transport import DhanOrderTransport

register_broker_extensions(
    "dhan",
    [
        DhanDepth20Extension,
        DhanDepth200Extension,
        DhanSuperOrderExtension,
        DhanForeverOrderExtension,
    ],
)
register_data_adapter("dhan", DhanDataProvider)
register_execution_provider("dhan", DhanOrderTransport)

from tradex.runtime.broker_plugin import BrokerPlugin, register_broker_plugin

register_broker_plugin(
    BrokerPlugin(
        broker_id="dhan",
        env_file=".env.local",
        default_mode="market",
        supported_modes=frozenset({"market", "trade"}),
        is_live=True,
    )
)
