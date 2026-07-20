"""Service-provider interfaces for broker integrations.

This module mirrors Trade_J's SPI concepts while staying idiomatic for Python.

.. note:: All brokers should implement ``MarketDataGateway`` from
   ``domain.ports.broker_adapter.BrokerAdapter`` / concrete gateways.
"""

from __future__ import annotations

from enum import Enum


class BrokerSource(str, Enum):
    """Broker provider identity."""

    DHAN = "dhan"
    UPSTOX = "upstox"
    PAPER = "paper"
