"""Trade_XV2 Broker — clean broker module.

Canonical domain types are imported from ``brokers.common.core.domain``.
Dhan-specific types and infrastructure come from ``brokers.dhan``.
"""

from brokers.common.core.domain import (
    Holding,
    Order,
    OrderResponse,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    Side,
    Trade,
    Validity,
)
from brokers.dhan import (
    Balance,
    BrokerFactory,
    BrokerGateway,
    DhanConnection,
    DhanHttpClient,
    Exchange,
    Instrument,
    InstrumentLoader,
    InstrumentType,
    InstrumentNotFoundError,
    MarketDepth,
    OptionType,
    Quote,
    SymbolResolver,
)

# Backward-compatibility alias — some code uses OrderSide instead of Side.
OrderSide = Side

__all__ = [
    # Canonical domain types (from brokers.common.core.domain)
    "Holding",
    "Order",
    "OrderResponse",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Position",
    "ProductType",
    "Side",
    "Trade",
    "Validity",
    # Dhan-specific types (from brokers.dhan)
    "Balance",
    "Exchange",
    "Instrument",
    "InstrumentLoader",
    "InstrumentNotFoundError",
    "InstrumentType",
    "MarketDepth",
    "OptionType",
    "Quote",
    # Infrastructure (from brokers.dhan)
    "BrokerFactory",
    "BrokerGateway",
    "DhanConnection",
    "DhanHttpClient",
    "SymbolResolver",
]
