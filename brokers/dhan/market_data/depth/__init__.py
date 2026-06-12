"""Market depth package for Dhan.

Provides 20-level market depth data for instruments.
"""

from __future__ import annotations

from brokers.dhan.market_data.depth.provider import DhanMarketDepthProvider

__all__ = ["DhanMarketDepthProvider"]
