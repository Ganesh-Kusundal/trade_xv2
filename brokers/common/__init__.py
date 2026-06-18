"""Broker-agnostic core types and interfaces.

This subpackage contains the canonical domain types, abstract interfaces,
and shared utilities used by all broker adapters (Dhan, Upstox, Paper).

Import Direction Rule
---------------------
brokers.common → broker-agnostic core (NEVER imports broker-specific code)
brokers.dhan → Dhan-specific adapter (imports from brokers.common)
brokers.upstox → Upstox-specific adapter (imports from brokers.common)
brokers.paper → Paper/mock trading adapter (imports from brokers.common)
"""
from __future__ import annotations

# Export common types
from brokers.common.core.domain import (
    Balance,
    DepthLevel,
    Holding,
    MarketDepth,
    Order,
    OrderResponse,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    Quote,
    Side,
    Trade,
    Validity,
)

# Export common interfaces
from brokers.common.gateway import MarketDataGateway
from brokers.common.factory import BrokerProviderFactory

# Export field mapping protocol and default implementation
from brokers.common.core.models import FieldMapping
from brokers.common.core.field_mapping import DefaultFieldMapping

# Backward-compatibility alias
OrderSide = Side

__all__ = [
    # Domain types
    "Balance",
    "DepthLevel",
    "Holding",
    "MarketDepth",
    "Order",
    "OrderResponse",
    "OrderStatus",
    "OrderType",
    "OrderSide",  # Backward-compat alias
    "Position",
    "ProductType",
    "Quote",
    "Side",
    "Trade",
    "Validity",
    # Abstract interfaces
    "MarketDataGateway",
    "BrokerProviderFactory",
    # Field mapping
    "FieldMapping",
    "DefaultFieldMapping",
]
