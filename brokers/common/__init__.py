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

from brokers.common.factory import BrokerProviderFactory
from domain.ports.broker_adapter import BrokerAdapter as MarketDataGateway

__all__ = [
    "BrokerProviderFactory",
    "MarketDataGateway",
]
