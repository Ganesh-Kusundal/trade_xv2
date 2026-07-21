"""Upstox capability groups — deep modules composing adapter clusters."""

from brokers.providers.upstox.capabilities.instruments import InstrumentsCapability
from brokers.providers.upstox.capabilities.market_data import MarketDataCapability
from brokers.providers.upstox.capabilities.orders import OrdersCapability
from brokers.providers.upstox.capabilities.portfolio import PortfolioCapability
from brokers.providers.upstox.capabilities.snapshot import upstox_capabilities
from brokers.providers.upstox.capabilities.streaming import StreamingCapability

__all__ = [
    "InstrumentsCapability",
    "MarketDataCapability",
    "OrdersCapability",
    "PortfolioCapability",
    "StreamingCapability",
    "upstox_capabilities",
]
