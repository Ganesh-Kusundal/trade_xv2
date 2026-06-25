"""Composer layer — application-level orchestration consuming coordinator interfaces.

The composer layer sits between the application/trading logic and the broker
coordination infrastructure. It provides:

- MarketDataComposer: Unified interface for historical data and streams
- ExecutionComposer: Order execution with routing and quota management
- Factory functions to bootstrap composers from injected dependencies

This layer ensures application code never calls broker gateways directly;
all calls go through coordinators with proper routing, quota, and provenance.
"""

from application.composer.execution import ExecutionComposer
from application.composer.factory import create_composers
from application.composer.market_data import MarketDataComposer

__all__ = [
    "ExecutionComposer",
    "MarketDataComposer",
    "create_composers",
]
