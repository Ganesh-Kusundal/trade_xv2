"""Service-provider interfaces for broker integrations.

This module mirrors Trade_J's SPI concepts while staying idiomatic for Python.

.. note:: All brokers should implement ``BrokerAdapter`` from
   ``domain.ports.broker_adapter.BrokerAdapter`` / concrete gateways.
"""

from __future__ import annotations
