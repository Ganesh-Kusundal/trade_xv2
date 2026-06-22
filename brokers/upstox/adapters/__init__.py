"""Upstox gateway adapters — extracted from god-class gateway.py.

Each adapter encapsulates a single responsibility:
- MarketDataAdapter: HTTP market data operations (LTP, Quote, Depth)
- HistoricalAdapter: Historical candle fetching and timeframe mapping
- SymbolResolverAdapter: Instrument key resolution and exchange mapping
- StreamManagerAdapter: WebSocket subscription lifecycle management
- TickTranslatorAdapter: Raw tick payload to canonical Quote translation
- OrderAdapter: Order placement and cancellation
- PortfolioAdapter: Portfolio, positions, holdings, and funds queries

The main UpstoxBrokerGateway acts as a thin facade delegating to these adapters.
"""

from __future__ import annotations

from brokers.upstox.adapters.market_data_adapter import MarketDataAdapter
from brokers.upstox.adapters.historical_adapter import HistoricalAdapter
from brokers.upstox.adapters.symbol_resolver import SymbolResolverAdapter
from brokers.upstox.adapters.stream_manager import StreamManagerAdapter
from brokers.upstox.adapters.tick_translator import TickTranslatorAdapter
from brokers.upstox.adapters.order_adapter import OrderAdapter
from brokers.upstox.adapters.portfolio_adapter import PortfolioAdapter

__all__ = [
    "MarketDataAdapter",
    "HistoricalAdapter",
    "SymbolResolverAdapter",
    "StreamManagerAdapter",
    "TickTranslatorAdapter",
    "OrderAdapter",
    "PortfolioAdapter",
]
