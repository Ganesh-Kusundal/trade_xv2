"""Symbol Resolution Interceptor.

Broker-agnostic interceptor that auto-maps canonical symbols (e.g., "RELIANCE", "NSE")
to broker-specific API identifiers (instrument_key, security_id, token, etc.).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from brokers.common.instrument_cache import InstrumentCacheManager

logger = logging.getLogger(__name__)


@dataclass
class ResolvedSymbol:
    """Result of symbol resolution."""

    broker: str
    symbol: str
    exchange: str
    api_key: str  # Broker-specific primary identifier
    api_metadata: dict  # Extra fields (exchange_segment, segment, etc.)
    raw_row: dict  # Full SQLite row for advanced use


class SymbolResolutionInterceptor:
    """Intercepts symbol+exchange requests and resolves to broker-specific IDs."""

    def __init__(self, cache_mgr: InstrumentCacheManager):
        self.cache = cache_mgr
        self._memory_cache: dict[tuple[str, str, str], ResolvedSymbol] = {}

    def resolve(
        self,
        broker: str,
        symbol: str,
        exchange: str = "NSE",
    ) -> ResolvedSymbol | None:
        """Resolve a canonical symbol+exchange to broker-specific API key.

        Args:
            broker: "upstox", "dhan", "zerodha", etc.
            symbol: e.g., "RELIANCE"
            exchange: e.g., "NSE" (canonical exchange name)

        Returns:
            ResolvedSymbol with api_key set to broker-specific identifier, or None if not found
        """
        cache_key = (broker, symbol, exchange)

        # 1. Check memory cache (hot path)
        if cache_key in self._memory_cache:
            return self._memory_cache[cache_key]

        # 2. Ensure broker cache is valid
        if not self.cache.is_cache_valid(broker):
            logger.warning(f"{broker} instrument cache invalid or expired")
            return None

        # 3. Resolve from SQLite via adapter
        row = self.cache.resolve_symbol(broker, symbol, exchange)
        if not row:
            logger.debug(f"Symbol {symbol}.{exchange} not found in {broker} cache")
            return None

        adapter = self.cache.get_adapter(broker)
        resolved = ResolvedSymbol(
            broker=broker,
            symbol=symbol,
            exchange=exchange,
            api_key=adapter.build_api_key(row),
            api_metadata=adapter.build_api_metadata(row),
            raw_row=row,
        )

        # Cache in memory for future calls
        self._memory_cache[cache_key] = resolved
        return resolved

    def resolve_many(
        self,
        broker: str,
        symbols: list[tuple[str, str]],
    ) -> list[ResolvedSymbol]:
        """Batch resolve multiple symbols.

        Args:
            broker: "upstox", "dhan", etc.
            symbols: list of (symbol, exchange) tuples

        Returns:
            List of successfully resolved symbols
        """
        results = []
        for symbol, exchange in symbols:
            resolved = self.resolve(broker, symbol, exchange)
            if resolved:
                results.append(resolved)
        return results

    def invalidate(self, broker: str | None = None):
        """Clear memory cache for a broker or all brokers.

        Args:
            broker: If provided, only clear cache for this broker.
                   If None, clear all cached symbols.
        """
        if broker is None:
            self._memory_cache.clear()
            logger.debug("Cleared all symbol resolution caches")
        else:
            keys_to_delete = [k for k in self._memory_cache if k[0] == broker]
            for k in keys_to_delete:
                del self._memory_cache[k]
            logger.debug(f"Cleared symbol resolution cache for {broker}")

    def get_cache_stats(self) -> dict:
        """Get cache statistics for monitoring."""
        return {
            "cached_symbols": len(self._memory_cache),
            "brokers_cached": len(set(k[0] for k in self._memory_cache.keys())),
        }
