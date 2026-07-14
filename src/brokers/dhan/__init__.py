"""DhanHQ broker adapter package — clean architecture.

Canonical domain types (Order, Position, Holding, Trade, Side, OrderStatus,
OrderType, ProductType, Validity, FundLimits) live in ``domain``::

    from domain import Order, Side, OrderStatus
    from brokers.dhan import Exchange, DhanInstrument
"""

# ── Dhan-specific domain types ──────────────────────────────────────────────
from brokers.dhan.streaming.connection import DhanConnection
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
from brokers.dhan.portfolio.reconciliation import DhanReconciliationService

# ── Infrastructure ──────────────────────────────────────────────────────────
from brokers.dhan.resolver import SymbolResolver

# Registers Dhan-specific status strings (PLACED, TRIGGERED, CLOSED, ...) with
# StatusMapperRegistry — import is for its registration side effect only.
import brokers.dhan.status_mapper  # noqa: F401
from brokers.dhan.websocket import DhanMarketFeed, DhanOrderStream, PollingMarketFeed
from domain import Balance, DepthLevel, MarketDepth, Quote, ReconciliationReport

__all__ = [
    "DHAN_SEGMENTS",
    # Exceptions
    "AuthenticationError",
    # Domain — Dhan-specific types
    "Balance",
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
from infrastructure.adapter_factory import (
    register_broker_extensions,
    register_data_adapter,
    register_execution_provider,
)
from brokers.dhan.data.data_provider import DhanDataProvider
from brokers.dhan.extensions.depth20 import DhanDepth20Extension
from brokers.dhan.extensions.depth200 import DhanDepth200Extension
from brokers.dhan.extensions.forever_order import DhanForeverOrderExtension
from brokers.dhan.extensions.super_order import DhanSuperOrderExtension
from brokers.dhan.api.transport import DhanOrderTransport

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

from infrastructure.broker_plugin import BrokerPlugin, register_broker_plugin

def _load_dhan_capabilities():
    from brokers.dhan.config.capabilities import dhan_capabilities
    return dhan_capabilities()


register_broker_plugin(
    BrokerPlugin(
        broker_id="dhan",
        env_file=".env.local",
        default_mode="market",
        supported_modes=frozenset({"market", "trade"}),
        is_live=True,
        capabilities_loader=_load_dhan_capabilities,
    )
)

from domain.market.segment_registry import register_segment_mapper
from brokers.dhan.segments import DhanSegmentMapper

register_segment_mapper("dhan", DhanSegmentMapper)
