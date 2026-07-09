"""Backward-compat re-export — moved to ``tradex.runtime.extensions``."""
from __future__ import annotations

from tradex.runtime.extensions import (  # noqa: F401, F403
    ExtensionBundle,
    ExtensionRegistry,
    get_extension_factory,
    register_extension_factory,
)
# Private API — test code imports this directly
from tradex.runtime.extensions import _extension_factories  # noqa: F401
