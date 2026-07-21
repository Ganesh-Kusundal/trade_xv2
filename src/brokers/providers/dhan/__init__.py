"""DhanHQ broker adapter package — clean architecture.

Canonical domain types (Order, Position, Holding, Trade, Side, OrderStatus,
OrderType, ProductType, Validity, FundLimits) live in ``domain``::

    from domain.entities import Order
    from domain.enums import Side, OrderStatus
    from brokers.providers.dhan import Exchange, DhanInstrument
"""

# ── Dhan-specific domain types ──────────────────────────────────────────────
# Registers Dhan-specific status strings (PLACED, TRIGGERED, CLOSED, ...) with
# StatusMapperRegistry — import is for its registration side effect only.
import brokers.providers.dhan.status_mapper  # noqa: F401
from brokers.providers.dhan._dhan_types import (
    DhanInstrument,
    Exchange,
    InstrumentType,
    OptionType,
)

# ── Exceptions ──────────────────────────────────────────────────────────────
from brokers.providers.dhan.exceptions import (
    AuthenticationError,
    ConfigurationError,
    DhanError,
    InstrumentNotFoundError,
    MarketDataError,
    OrderError,
    RateLimitError,
)
from brokers.providers.dhan.identity import (
    DHAN_SEGMENTS,
    DhanIdentityError,
    DhanIdentityProvider,
    DhanIdentitySource,
    DhanInstrumentRef,
    coerce_identity_provider,
    is_dhan_segment,
)
from brokers.providers.dhan.loader import InstrumentLoader
from brokers.providers.dhan.portfolio.reconciliation import DhanReconciliationService

# ── Infrastructure ──────────────────────────────────────────────────────────
from brokers.providers.dhan.resolver import SymbolResolver
from brokers.providers.dhan.streaming.connection import DhanConnection
from brokers.providers.dhan.websocket import DhanMarketFeed, DhanOrderStream, PollingMarketFeed
from domain.entities import (
    Balance,
    DepthLevel,
    MarketDepth,
    Quote,
)
from domain.reconciliation import ReconciliationReport

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
    "DhanInstrument",
    "DhanInstrumentRef",
    # WebSocket
    "DhanMarketFeed",
    "DhanOrderStream",
    # Reconciliation
    "DhanReconciliationService",
    "Exchange",
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
from brokers.providers.dhan.api.transport import DhanOrderTransport
from brokers.providers.dhan.market_data.data_provider import DhanDataProvider
from brokers.providers.dhan.extensions.depth20 import DhanDepth20Extension
from brokers.providers.dhan.extensions.depth200 import DhanDepth200Extension
from brokers.providers.dhan.extensions.forever_order import DhanForeverOrderExtension
from brokers.providers.dhan.extensions.super_order import DhanSuperOrderExtension
from infrastructure.adapter_factory import (
    register_broker_extensions,
    register_data_adapter,
    register_execution_provider,
)

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
    from brokers.providers.dhan.config.capabilities import dhan_capabilities

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

from brokers.providers.dhan.segments import DhanSegmentMapper
from domain.market.segment_registry import register_segment_mapper

register_segment_mapper("dhan", DhanSegmentMapper)
