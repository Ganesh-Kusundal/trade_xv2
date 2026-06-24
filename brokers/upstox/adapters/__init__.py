"""Upstox gateway adapters — extracted from god-class gateway.py.

Each adapter encapsulates a single responsibility:
- MarketDataAdapter: HTTP market data operations (LTP, Quote, Depth)
- HistoricalAdapter: Historical candle fetching and timeframe mapping
- StreamManagerAdapter: WebSocket subscription lifecycle management
- TickTranslatorAdapter: Raw tick payload to canonical Quote translation
- PortfolioAdapter: Portfolio, positions, holdings, and funds queries

The main UpstoxBrokerGateway acts as a thin facade delegating to these adapters.
"""

from __future__ import annotations

from brokers.upstox.adapters.market_data_adapter import MarketDataAdapter
from brokers.upstox.adapters.historical_adapter import HistoricalAdapter
from brokers.upstox.adapters.stream_manager import StreamManagerAdapter
from brokers.upstox.adapters.tick_translator import TickTranslatorAdapter
from brokers.upstox.adapters.portfolio_adapter import PortfolioAdapter

__all__ = [
    "MarketDataAdapter",
    "HistoricalAdapter",
    "StreamManagerAdapter",
    "TickTranslatorAdapter",
    "PortfolioAdapter",
]
