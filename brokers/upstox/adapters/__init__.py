"""Upstox gateway adapters — extracted from god-class gateway.py.

Each adapter encapsulates a single responsibility:
- HistoricalAdapter: Historical candle fetching and timeframe mapping
- StreamManagerAdapter: WebSocket subscription lifecycle management
- TickTranslatorAdapter: Raw tick payload to canonical Quote translation
- PortfolioAdapter: Portfolio, positions, holdings, and funds queries

Gateway-level adapters compose lower-level adapters into focused public APIs:
- MarketDataGateway: LTP, quote, depth, history, chains, lifecycle
- OrderGateway: place, cancel, modify, orderbook, trade book
- StreamingGateway: WebSocket streams, tick parsing, depth streaming
- PortfolioGateway: funds, positions, holdings

The main UpstoxBrokerGateway acts as a thin facade delegating to these adapters.

P-2.2: Removed duplicate MarketDataAdapter - use brokers.upstox.market_data.market_data_adapter
which implements the MarketDataProvider ABC correctly.
"""

from __future__ import annotations

from brokers.upstox.adapters.historical_adapter import HistoricalAdapter
from brokers.upstox.adapters.market_data_gateway import MarketDataGateway
from brokers.upstox.adapters.order_gateway import OrderGateway
from brokers.upstox.adapters.portfolio_adapter import PortfolioAdapter
from brokers.upstox.adapters.portfolio_gateway import PortfolioGateway
from brokers.upstox.adapters.stream_manager import StreamManagerAdapter
from brokers.upstox.adapters.streaming_gateway import StreamingGateway
from brokers.upstox.adapters.tick_translator import TickTranslatorAdapter

__all__ = [
    "HistoricalAdapter",
    "MarketDataGateway",
    "OrderGateway",
    "PortfolioAdapter",
    "PortfolioGateway",
    "StreamManagerAdapter",
    "StreamingGateway",
    "TickTranslatorAdapter",
]
