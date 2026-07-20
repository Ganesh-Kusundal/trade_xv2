"""Broker plugin registry — re-export of the composition-root registry.

Keeps ``brokers.session`` self-contained for discovery/metadata without
importing concrete broker packages (preserves import-linter contracts).
"""

from __future__ import annotations

from infrastructure.broker_plugin import (
    BrokerPlugin,
    ensure_core_plugins,
    get_broker_plugin,
    list_broker_plugins,
    register_broker_plugin,
)

# Trigger entry-point discovery of out-of-tree plugins (runtime/ is allowed
# to import concrete broker packages; this module is the one sanctioned place).
from runtime.broker_discovery import discover_broker_plugins

__all__ = [
    "BrokerPlugin",
    "discover_broker_plugins",
    "ensure_core_plugins",
    "get_broker_plugin",
    "list_broker_plugins",
    "register_broker_plugin",
]
