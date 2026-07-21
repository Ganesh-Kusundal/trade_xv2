"""Dhan broker extensions — broker-specific capabilities as domain plugins.

Each extension wraps a Dhan-specific feature (depth_20, depth_200, super orders,
forever orders) behind the domain ``Extension`` ABC. Domain code never imports
these directly — it queries by name via ``instrument.get_extension("depth20")``.
"""

from brokers.providers.dhan.extensions.depth20 import DhanDepth20Extension
from brokers.providers.dhan.extensions.depth200 import DhanDepth200Extension

__all__ = ["DhanDepth20Extension", "DhanDepth200Extension"]
