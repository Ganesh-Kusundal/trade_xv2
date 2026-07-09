"""Runtime typing alias for the domain broker adapter port.

Canonical type: :class:`domain.ports.broker_adapter.BrokerAdapter`.

``MarketDataGateway`` is kept as a historical name used in runtime/CLI type
annotations; it is the same object as ``BrokerAdapter``.
"""

from __future__ import annotations

from domain.ports.broker_adapter import BrokerAdapter
from domain.ports.broker_adapter import BrokerAdapter as MarketDataGateway
from tradex.runtime.capabilities import BrokerCapabilities

__all__ = [
    "BrokerAdapter",
    "BrokerCapabilities",
    "MarketDataGateway",
]
