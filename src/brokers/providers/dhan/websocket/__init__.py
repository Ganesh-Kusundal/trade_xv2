"""Dhan WebSocket adapter — real-time market data and order updates.

Task 5.1: Split the former monolithic ``websocket.py`` into a package
organised by responsibility.  This ``__init__.py`` re-exports the three
public classes so that all existing import paths continue to work:

    from brokers.providers.dhan.websocket import DhanMarketFeed
    from brokers.providers.dhan.websocket import DhanOrderStream
    from brokers.providers.dhan.websocket import PollingMarketFeed
"""

from brokers.providers.dhan.websocket.market_feed import DhanMarketFeed
from brokers.providers.dhan.websocket.order_stream import DhanOrderStream
from brokers.providers.dhan.websocket.polling_feed import PollingMarketFeed

__all__ = [
    "DhanMarketFeed",
    "DhanOrderStream",
    "PollingMarketFeed",
]
