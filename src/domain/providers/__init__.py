"""Provider Framework — the central data/execution abstraction.

Providers replace scattered broker references with a single, unified
interface.  The ProviderRegistry is created at composition root and
injected into aggregates and services.

Submodules:
    protocols.py — DataProvider, ExecutionProvider, Subscription
    registry.py  — ProviderRegistry
"""

from __future__ import annotations

from domain.providers.registry import ProviderRegistry
from domain.ports.protocols import DataProvider, ExecutionProvider, Subscription

__all__ = [
    "DataProvider",
    "ExecutionProvider",
    "ProviderRegistry",
    "Subscription",
]
