"""Market data adapter — HTTP-based market data operations.

Responsibility: Fetch LTP, quotes, and market depth from Upstox V2 API.
Thread-safe: All methods are stateless and thread-safe.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from brokers.common.core.domain import MarketDepth, Quote

from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
from brokers.upstox.mappers.price_parser import UpstoxPriceParser

if TYPE_CHECKING:
    from brokers.upstox.broker import UpstoxBroker

logger = logging.getLogger(__name__)


class MarketDataAdapter:
    """Adapter for HTTP-based market data operations.
    
    Encapsulates all market data fetch operations (LTP, Quote, Depth)
    that delegate to Upstox's V2 market data client.
    
    Thread Safety:
        All methods are stateless and thread-safe. No instance state is mutated.
    
    Example::
    
        adapter = MarketDataAdapter(broker)
        ltp = adapter.get_ltp("RELIANCE", "NSE")
        quote = adapter.get_quote("RELIANCE", "NSE")
        depth = adapter.get_depth("RELIANCE", "NSE")
    """
    
    def __init__(self, broker: UpstoxBroker) -> None:
        """Initialize with broker facade.
        
        Args:
            broker: UpstoxBroker instance providing access to market_data_v2 client
        """
        self._broker = broker
    
    def get_ltp(
        self,
        symbol: str,
        exchange: str,
        instrument_key: str,
    ) -> Decimal:
        """Fetch last traded price for an instrument.
        
        Args:
            symbol: Canonical trading symbol (e.g., "RELIANCE")
            exchange: Exchange segment (e.g., "NSE", "BSE")
            instrument_key: Resolved Upstox instrument key (e.g., "NSE_EQ|RELIANCE")
            
        Returns:
            Last traded price as Decimal, or Decimal("0") if not found
        """
        body = self._broker.market_data_v2.get_ltp([instrument_key])
        data = body.get("data", {})
        for _, v in data.items():
            if isinstance(v, dict) and "last_price" in v:
                return UpstoxPriceParser.parse(v["last_price"])
        return Decimal("0")
    
    def get_quote(
        self,
        symbol: str,
        exchange: str,
        instrument_key: str,
    ) -> Quote:
        """Fetch full quote with OHLCV for an instrument.
        
        Args:
            symbol: Canonical trading symbol
            exchange: Exchange segment
            instrument_key: Resolved Upstox instrument key
            
        Returns:
            Quote dataclass with OHLCV data, or empty Quote if not found
        """
        body = self._broker.market_data_v2.get_quote([instrument_key])
        data = body.get("data", {})
        for _, v in data.items():
            if isinstance(v, dict) and "last_price" in v:
                ohlc = v.get("ohlc", {})
                return Quote(
                    symbol=symbol,
                    ltp=UpstoxPriceParser.parse(v.get("last_price", 0)),
                    open=UpstoxPriceParser.parse(ohlc.get("open", 0)),
                    high=UpstoxPriceParser.parse(ohlc.get("high", 0)),
                    low=UpstoxPriceParser.parse(ohlc.get("low", 0)),
                    close=UpstoxPriceParser.parse(ohlc.get("close", 0)),
                    volume=int(v.get("volume", 0)),
                    change=UpstoxPriceParser.parse(v.get("net_change", 0)),
                )
        logger.warning(
            "quote_not_found",
            extra={"symbol": symbol, "exchange": exchange},
        )
        return Quote(symbol=symbol)
    
    def get_depth(
        self,
        symbol: str,
        exchange: str,
        instrument_key: str,
    ) -> MarketDepth:
        """Fetch order book depth for an instrument.
        
        Args:
            symbol: Canonical trading symbol
            exchange: Exchange segment
            instrument_key: Resolved Upstox instrument key
            
        Returns:
            MarketDepth with bid/ask levels, or empty MarketDepth if not found
        """
        body = self._broker.market_data_v2.get_order_book(instrument_key)
        data = body.get("data", {})
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, dict) and "depth" in v:
                    return UpstoxDomainMapper.to_market_depth(v)
        return MarketDepth()
