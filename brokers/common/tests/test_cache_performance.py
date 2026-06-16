"""Performance benchmarks for SQLite instrument cache.

Measures:
1. Cold start: First-time cache population from JSON
2. Warm start: Cache already populated, just load from SQLite
3. Single symbol resolution: SQLite query vs memory cache
4. Batch resolution: 100 symbols resolution time
5. Memory usage: SQLite vs in-memory dict
"""

import time
import tempfile
from pathlib import Path

import pytest

from brokers.common.instrument_cache import InstrumentCacheManager
from brokers.common.symbol_resolver import SymbolResolutionInterceptor
from brokers.upstox.instruments.cache_adapter import UpstoxInstrumentAdapter


class TestCachePerformance:
    """Performance benchmarks for instrument cache."""

    @pytest.fixture
    def cache_manager(self, tmp_path):
        """Create cache manager with temp database."""
        db_path = tmp_path / "perf_test.db"
        return InstrumentCacheManager(db_path=db_path)

    @pytest.fixture
    def sample_instruments(self):
        """Create 10k sample instruments for benchmarking."""
        from brokers.upstox.instruments.definition import UpstoxInstrumentDefinition

        instruments = []
        for i in range(10_000):
            if i < 5000:
                # Equity instruments
                inst = UpstoxInstrumentDefinition(
                    instrument_key=f"NSE_EQ|SYMBOL{i}",
                    symbol=f"SYMBOL{i}",
                    exchange="NSE",
                    exchange_segment="NSE_EQ",
                    instrument_type="EQUITY",
                    lot_size=1,
                    tick_size=0.05,
                )
            elif i < 7500:
                # Futures
                inst = UpstoxInstrumentDefinition(
                    instrument_key=f"NSE_FO|SYMBOL{i}26JUN25FUT",
                    symbol=f"SYMBOL{i}26JUN25FUT",
                    exchange="NFO",
                    exchange_segment="NSE_FO",
                    instrument_type="FUTURES",
                    expiry="2025-06-26",
                    lot_size=50,
                    tick_size=0.05,
                )
            else:
                # Options
                inst = UpstoxInstrumentDefinition(
                    instrument_key=f"NSE_FO|SYMBOL{i}26JUN25{i}CE",
                    symbol=f"SYMBOL{i}26JUN{i}CE",
                    exchange="NFO",
                    exchange_segment="NSE_FO",
                    instrument_type="OPTIONS",
                    expiry="2025-06-26",
                    strike_price=float(i * 10),
                    option_type="CE",
                    lot_size=50,
                    tick_size=0.05,
                )
            instruments.append(inst)
        return instruments

    def test_cold_cache_population(self, cache_manager, sample_instruments, benchmark):
        """Benchmark: Cold cache population (parse + insert 10k instruments)."""
        def populate_cache():
            adapter = UpstoxInstrumentAdapter(db_path=cache_manager.db_path)
            cache_manager.register_adapter(adapter)
            cache_manager.cache_instruments("upstox", sample_instruments)
            return cache_manager.get_instrument_count("upstox")

        result = benchmark(populate_cache)
        assert result == 10_000

    def test_warm_cache_load(self, cache_manager, sample_instruments, benchmark):
        """Benchmark: Warm cache load (SQLite already populated)."""
        # Pre-populate cache
        adapter = UpstoxInstrumentAdapter(db_path=cache_manager.db_path)
        cache_manager.register_adapter(adapter)
        cache_manager.cache_instruments("upstox", sample_instruments)

        # Benchmark validation time
        def validate_cache():
            return cache_manager.is_cache_valid("upstox")

        result = benchmark(validate_cache)
        assert result is True

    def test_single_resolution_sqlite(self, cache_manager, sample_instruments, benchmark):
        """Benchmark: Single symbol resolution from SQLite (no memory cache)."""
        # Pre-populate cache
        adapter = UpstoxInstrumentAdapter(db_path=cache_manager.db_path)
        cache_manager.register_adapter(adapter)
        cache_manager.cache_instruments("upstox", sample_instruments)

        # Create interceptor with fresh cache (no memory cache)
        interceptor = SymbolResolutionInterceptor(cache_manager)

        def resolve_symbol():
            return interceptor.resolve("upstox", "SYMBOL500", "NSE")

        result = benchmark(resolve_symbol)
        assert result is not None
        assert result.api_key == "NSE_EQ|SYMBOL500"

    def test_single_resolution_memory_cache(self, cache_manager, sample_instruments, benchmark):
        """Benchmark: Single symbol resolution from memory cache (hot path)."""
        # Pre-populate cache
        adapter = UpstoxInstrumentAdapter(db_path=cache_manager.db_path)
        cache_manager.register_adapter(adapter)
        cache_manager.cache_instruments("upstox", sample_instruments)

        # Create interceptor and warm up memory cache
        interceptor = SymbolResolutionInterceptor(cache_manager)
        interceptor.resolve("upstox", "SYMBOL500", "NSE")  # Warm up

        def resolve_symbol():
            return interceptor.resolve("upstox", "SYMBOL500", "NSE")

        result = benchmark(resolve_symbol)
        assert result is not None
        assert result.api_key == "NSE_EQ|SYMBOL500"

    def test_batch_resolution_100_symbols(self, cache_manager, sample_instruments, benchmark):
        """Benchmark: Batch resolution of 100 symbols."""
        # Pre-populate cache
        adapter = UpstoxInstrumentAdapter(db_path=cache_manager.db_path)
        cache_manager.register_adapter(adapter)
        cache_manager.cache_instruments("upstox", sample_instruments)

        # Create interceptor
        interceptor = SymbolResolutionInterceptor(cache_manager)

        symbols = [f"SYMBOL{i}" for i in range(100)]

        def resolve_batch():
            results = []
            for sym in symbols:
                resolved = interceptor.resolve("upstox", sym, "NSE")
                results.append(resolved)
            return results

        result = benchmark(resolve_batch)
        assert len(result) == 100
        assert all(r is not None for r in result)

    def test_search_performance(self, cache_manager, sample_instruments, benchmark):
        """Benchmark: Search by prefix across 10k instruments."""
        # Pre-populate cache
        adapter = UpstoxInstrumentAdapter(db_path=cache_manager.db_path)
        cache_manager.register_adapter(adapter)
        cache_manager.cache_instruments("upstox", sample_instruments)

        def search_prefix():
            return cache_manager.search("upstox", "SYMBOL123", limit=10)

        result = benchmark(search_prefix)
        assert len(result) <= 10

    def test_cache_size_metrics(self, cache_manager, sample_instruments):
        """Measure cache database size and memory footprint."""
        # Pre-populate cache
        adapter = UpstoxInstrumentAdapter(db_path=cache_manager.db_path)
        cache_manager.register_adapter(adapter)
        cache_manager.cache_instruments("upstox", sample_instruments)

        # Get database size
        db_size = cache_manager.db_path.stat().st_size
        print(f"\n  SQLite database size: {db_size / 1024:.1f} KB")
        print(f"  Instruments cached: {cache_manager.get_instrument_count('upstox')}")
        print(f"  Size per instrument: {db_size / 10_000:.1f} bytes")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--benchmark-only", "--benchmark-sort=min"])
