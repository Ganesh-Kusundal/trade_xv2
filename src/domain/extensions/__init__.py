"""Extension Framework — broker-specific capabilities as composable plugins.

Extensions are registered at startup and discovered at runtime.  Domain
code never references broker-specific types — it queries the registry
by capability name.

Submodules:
    base.py          — Extension ABC
    registry.py      — ExtensionRegistry (instrument capability discovery)
    broker_bundle.py — ExtensionBundle / BrokerExtensionRegistry (broker bundles)
"""

from __future__ import annotations

from domain.extensions.base import Extension
from domain.extensions.broker_bundle import (
    BrokerExtensionRegistry,
    ExtensionBundle,
    get_extension_factory,
    register_extension_factory,
)
from domain.extensions.order_capability import OrderCapabilityPort
from domain.extensions.registry import ExtensionRegistry

__all__ = [
    "BrokerExtensionRegistry",
    "Extension",
    "ExtensionBundle",
    "ExtensionRegistry",
    "OrderCapabilityPort",
    "get_extension_factory",
    "register_extension_factory",
]
