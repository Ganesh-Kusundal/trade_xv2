"""Symbol resolver adapter — instrument key resolution and exchange mapping.

Responsibility: Resolve canonical symbols to Upstox instrument keys and
map exchange segments to wire format.
Thread-safe: All methods are stateless and thread-safe.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from brokers.common.core.domain import ExchangeSegment

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
        2. Normal segment resolution for equities/F&O
        
        Args:
            symbol: Canonical trading symbol (e.g., "RELIANCE", "NIFTY")
            exchange: Exchange segment (e.g., "NSE", "NFO")
            
        Returns:
            Upstox instrument_key string (e.g., "NSE_EQ|RELIANCE")
            
        Note:
            For index symbols, checks config.indices.index_upstox_key first
            since indices use a different segment (NSE_INDEX) than equities.
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
        
        # 2. Normal segment resolution for equities/F&O
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
        
        return f"{segment}|{symbol}"
    
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
        
        mapping: dict[str, ExchangeSegment] = {
            "NSE": ExchangeSegment.NSE,
            "BSE": ExchangeSegment.BSE,
            "NFO": ExchangeSegment.NSE_FNO,
            "NSE_FNO": ExchangeSegment.NSE_FNO,
            "BFO": ExchangeSegment.BSE_FNO,
            "BSE_FNO": ExchangeSegment.BSE_FNO,
            "MCX": ExchangeSegment.MCX,
            "NSE_CURRENCY": ExchangeSegment.NSE_CURRENCY,
            "BSE_CURRENCY": ExchangeSegment.BSE_CURRENCY,
            "IDX_I": ExchangeSegment.IDX_I,
        }
        return mapping.get(exchange.upper(), ExchangeSegment.NSE)
