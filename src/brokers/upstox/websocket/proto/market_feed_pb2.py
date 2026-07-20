"""Generated Python stub for Upstox V3 MarketDataFeed.proto.

Re-exports from MarketDataFeed_pb2.
"""

from __future__ import annotations

try:
    from .MarketDataFeed_pb2 import (
        LTPC,
        OHLC,
        Feed,
        FeedResponse,
        FirstLevelWithGreeks,
        FullFeed,
        IndexFullFeed,
        MarketFullFeed,
        MarketInfo,
        MarketLevel,
        MarketOHLC,
        MarketStatus,
        OptionGreeks,
        Quote,
        RequestMode,
        Type,
    )
except ImportError:
    try:
        from MarketDataFeed_pb2 import (
            LTPC,
            OHLC,
            Feed,
            FeedResponse,
            FirstLevelWithGreeks,
            FullFeed,
            IndexFullFeed,
            MarketFullFeed,
            MarketInfo,
            MarketLevel,
            MarketOHLC,
            MarketStatus,
            OptionGreeks,
            Quote,
            RequestMode,
            Type,
        )
    except ImportError:
        # Fallback dummy class if import fails in unit tests
        class FeedResponse:
            pass

        class Feed:
            pass
