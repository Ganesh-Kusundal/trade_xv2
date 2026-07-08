"""Upstox broker extensions — broker-specific capabilities as domain plugins.

Each extension wraps an Upstox-specific feature (depth_30) behind the domain
``Extension`` ABC. Domain code never imports these directly — it queries by
name via ``instrument.get_extension("depth_30")``.
"""

from brokers.upstox.extensions.depth import UpstoxDepth30Extension

__all__ = ["UpstoxDepth30Extension"]
