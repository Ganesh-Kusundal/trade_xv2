"""Brokers runtime — thin coordinators for the Trading OS mini-OS.

These managers orchestrate lifecycles (subscriptions, history, quotes,
execution, capability discovery, symbol mapping) over the existing
``DataProvider`` / ``ExecutionProvider`` ports and the rich ``Instrument``
objects. They contain no market logic of their own — that lives on the domain
objects and broker plugins.
"""

from __future__ import annotations

from brokers.runtime.bundle import RuntimeBundle
from brokers.runtime.capability_manager import CapabilityManager
from brokers.runtime.event_bus import EventBusFacade
from brokers.runtime.execution_manager import ExecutionManager
from brokers.runtime.historical_manager import HistoricalManager
from brokers.runtime.quote_manager import QuoteManager
from brokers.runtime.subscription_manager import SubscriptionManager
from brokers.runtime.symbol_registry import SymbolRegistry

__all__ = [
    "CapabilityManager",
    "EventBusFacade",
    "ExecutionManager",
    "HistoricalManager",
    "QuoteManager",
    "RuntimeBundle",
    "SubscriptionManager",
    "SymbolRegistry",
]