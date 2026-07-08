"""Extension Framework — broker-specific capabilities as composable plugins.

Extensions are registered at startup and discovered at runtime.  Domain
code never references broker-specific types — it queries the registry
by capability name.

Submodules:
    base.py      — Extension ABC
    registry.py  — ExtensionRegistry
"""

from __future__ import annotations

from domain.extensions.base import Extension
from domain.extensions.registry import ExtensionRegistry

__all__ = [
    "Extension",
    "ExtensionRegistry",
]
