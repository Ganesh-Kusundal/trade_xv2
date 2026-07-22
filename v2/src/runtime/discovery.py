"""Broker plugin discovery via entry points + explicit fallback imports."""

from __future__ import annotations

import importlib
import importlib.metadata
from typing import Any

from domain.enums import BrokerId
from plugins.brokers.registry import get_plugin, list_plugins

_FALLBACK_MODULES = (
    "plugins.brokers.paper",
    "plugins.brokers.dhan",
    "plugins.brokers.upstox",
)


def discover_brokers() -> dict[BrokerId, Any]:
    """Load `tradex.brokers` entry points; if empty, call known register() imports."""
    eps = list(importlib.metadata.entry_points(group="tradex.brokers"))
    loaded_any = False
    for ep in eps:
        try:
            ep.load()()
            loaded_any = True
        except Exception:
            # missing optional plugin (e.g. paper mid-parallel build) — keep going
            continue

    if not loaded_any:
        # ponytail: editable installs sometimes hide entry points — explicit imports
        for mod_name in _FALLBACK_MODULES:
            try:
                importlib.import_module(mod_name).register()
            except ImportError:
                continue

    return {broker_id: get_plugin(broker_id) for broker_id in list_plugins()}
