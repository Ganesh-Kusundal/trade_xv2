"""Backward-compat re-export — MarketDataGateway is now BrokerAdapter.

The old ``MarketDataGateway`` ABC has been removed.  Use
:class:`domain.ports.broker_adapter.BrokerAdapter` directly instead.
This module exists only so code that says::

    from brokers.common.gateway import MarketDataGateway

continues to work during the transition.
"""

from __future__ import annotations

from domain.ports.broker_adapter import BrokerAdapter as MarketDataGateway
from domain.ports.broker_adapter import BrokerAdapter
from brokers.common.capabilities import BrokerCapabilities

__all__ = [
    "BrokerAdapter",
    "BrokerCapabilities",
    "MarketDataGateway",
]
