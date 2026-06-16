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
    InstrumentNotFoundError,
    InstrumentType,
    MarketDepth,
    OptionType,
    Quote,
    SymbolResolver,
)

# Backward-compatibility alias — some code uses OrderSide instead of Side.
OrderSide = Side

__all__ = [
    # Dhan-specific types (from brokers.dhan)
    "Balance",
    # Infrastructure (from brokers.dhan)
    "BrokerFactory",
    "BrokerGateway",
    "DhanConnection",
    "DhanHttpClient",
    "Exchange",
    # Canonical domain types (from brokers.common.core.domain)
    "Holding",
    "Instrument",
    "InstrumentLoader",
    "InstrumentNotFoundError",
    "InstrumentType",
    "MarketDepth",
    "OptionType",
    "Order",
    "OrderResponse",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Position",
    "ProductType",
    "Quote",
    "Side",
    "SymbolResolver",
    "Trade",
    "Validity",
]
