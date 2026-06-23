"""Symbol resolver adapter — instrument key resolution and exchange mapping.

Responsibility: Resolve canonical symbols to Upstox instrument keys and
map exchange segments to wire format.
Thread-safe: All methods are stateless and thread-safe.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from brokers.common.core.domain import ExchangeSegment
from brokers.common.core.exchange_segments import parse_segment

from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper

if TYPE_CHECKING:
    from brokers.upstox.broker import UpstoxBroker


class SymbolResolverAdapter:
    """Adapter for symbol resolution and exchange segment mapping.
    
    Encapsulates instrument key resolution logic including:
    - Index symbol detection and hardcoded mapping
    - Normal equity/F&O segment resolution
    - Exchange segment to wire format conversion
    
    Thread Safety:
        All methods are stateless and thread-safe. Delegates to the broker's
        instrument_resolver which maintains its own thread-safe state.
    
    Example::
    
        resolver = SymbolResolverAdapter(broker)
        key = resolver.resolve_key("RELIANCE", "NSE")
        segment = resolver.resolve_exchange_segment("NFO")
    """
    
    def __init__(self, broker: UpstoxBroker) -> None:
        """Initialize with broker facade.
        
        Args:
            broker: UpstoxBroker instance providing access to instrument_resolver
        """
        self._broker = broker
    
    def resolve_key(self, symbol: str, exchange: str) -> str:
        """Resolve canonical symbol to Upstox instrument_key.
        
        Resolution priority:
        1. Hardcoded index mapping (NIFTY, BANKNIFTY, etc.) → NSE_INDEX segment
        2. Instrument master lookup (returns ISIN for equities)
        3. Fallback: construct key from segment|symbol
        
        Args:
            symbol: Canonical trading symbol (e.g., "RELIANCE", "NIFTY")
            exchange: Exchange segment (e.g., "NSE", "NFO")
            
        Returns:
            Upstox instrument_key string (e.g., "NSE_EQ|INE002A01018")
            
        Note:
            For index symbols, checks config.indices.index_upstox_key first
            since indices use a different segment (NSE_INDEX) than equities.
            
        Important:
            Upstox V3 historical API requires:
            - ISIN format for equities: NSE_EQ|INE002A01018
            - Exact symbol format for indices: NSE_INDEX|Nifty 50
            Spaces in instrument keys are valid for indices but NOT for equities.
        """
        from config.indices import index_upstox_key
        
        # 1. Check hardcoded index mapping first
        idx_key = index_upstox_key(symbol)
        if idx_key is not None:
            # Verify the key resolves (the asset JSON includes indices)
            defn = self._broker.instrument_resolver.resolve(instrument_key=idx_key)
            if defn:
                return defn.instrument_key
            # Fall through — return the hardcoded key anyway (it's a known index)
            return idx_key
        
        # 2. Try instrument master lookup (returns ISIN for equities)
        segment = UpstoxDomainMapper.segment_to_wire(exchange)
        if segment == 'NSE':
            segment = 'NSE_EQ'
        elif segment == 'BSE':
            segment = 'BSE_EQ'
        
        defn = self._broker.instrument_resolver.resolve(
            symbol=symbol,
            exchange_segment=segment,
        )
        if defn:
            return defn.instrument_key
        
        # 3. Fallback: construct key, but warn if it contains spaces
        fallback_key = f"{segment}|{symbol}"
        if ' ' in symbol:
            import logging
            logging.getLogger(__name__).warning(
                "Instrument key contains space: %s. This may fail for historical API. "
                "Consider using the correct symbol from instrument master.",
                fallback_key
            )
        return fallback_key
    
    @staticmethod
    def resolve_exchange_segment(exchange: str, symbol: str = "") -> ExchangeSegment:
        """Map user-facing exchange string to canonical ExchangeSegment.
        
        For recognised index symbols (NIFTY, BANKNIFTY, etc.) the segment is
        set to IDX_I regardless of the exchange string.
        
        Args:
            exchange: User-facing exchange string (e.g., "NSE", "NFO")
            symbol: Optional symbol for index detection
            
        Returns:
            Canonical ExchangeSegment enum value
        """
        from config.indices import index_upstox_key
        
        # Index symbols use a dedicated segment
        if symbol:
            if index_upstox_key(symbol) is not None:
                return ExchangeSegment.IDX_I
        
        parsed = parse_segment(exchange)
        if parsed is None:
            raise ValueError(f"Unknown exchange segment: {exchange!r}")
        return parsed
