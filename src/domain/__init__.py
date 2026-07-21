"""Domain layer — canonical types and entities for TradeXV2.

This module re-exports the most commonly used domain types for convenience.
New code should import from the owning submodule directly (e.g.,
``from domain.enums import Side``).
"""

__version__ = "0.1.0"

# Re-export commonly used types for backward compatibility
from domain.entities import (
    Balance,
    Holding,
    Instrument,
    MarketDepth,
    Order,
    Position,
    Quote,
    Trade,
)
from domain.entities.market import DepthLevel
from domain.entities.market import DepthLevel
from domain.enums import (
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)

__all__ = [
    "Balance",
    "Instrument",
    "MarketDepth",
    "Order",
    "OrderStatus",
    "OrderType",
    "Position",
    "ProductType",
    "Quote",
    "Side",
    "Trade",
    "Validity",
]
