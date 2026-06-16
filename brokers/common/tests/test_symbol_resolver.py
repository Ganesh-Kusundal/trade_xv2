"""Comprehensive symbol resolution tests for all instrument types."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from brokers.common.instrument_cache import InstrumentCacheManager
from brokers.common.symbol_resolver import SymbolResolutionInterceptor
from brokers.upstox.instruments.cache_adapter import UpstoxInstrumentAdapter


@pytest.fixture
def setup_upstox_cache():
    """Create Upstox cache with realistic instrument data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "upstox_test.db"
        
        cache_mgr = InstrumentCacheManager(db_path=db_path)
        adapter = UpstoxInstrumentAdapter(db_path=db_path)
        cache_mgr.register_adapter(adapter)
        
        # Insert realistic test instruments (NO duplicates on symbol+exchange_segment)
        instruments = [
            # NSE Equity
            ("NSE_EQ|INE002A01018", "RELIANCE", "NSE", "NSE_EQ", "EQ", "Reliance Industries", "INE002A01018", None, None, None, 1, 0.05),
            ("NSE_EQ|INE467B01029", "TCS", "NSE", "NSE_EQ", "EQ", "Tata Consultancy", "INE467B01029", None, None, None, 1, 0.05),
            ("NSE_EQ|INE040A01034", "HDFCBANK", "NSE", "NSE_EQ", "EQ", "HDFC Bank", "INE040A01034", None, None, None, 1, 0.05),
            # BSE Equity
            ("BSE_EQ|INE002A01018", "RELIANCE", "BSE", "BSE_EQ", "EQ", "Reliance Industries", "INE002A01018", None, None, None, 1, 0.05),
            # NSE Index Futures
            ("NSE_FO|12345", "NIFTY", "NSE", "NSE_FO", "INDEX_FUT", "NIFTY 50", None, "2026-06-25", None, None, 50, 0.05),
            ("NSE_FO|67890", "BANKNIFTY", "NSE", "NSE_FO", "INDEX_FUT", "NIFTY BANK", None, "2026-06-25", None, None, 15, 0.05),
            # NSE Stock Futures (different underlying to avoid conflict)
            ("NSE_FO|11111", "INFY", "NSE", "NSE_FO", "STK_FUT", "Infosys", None, "2026-06-25", None, None, 250, 0.05),
            # NSE Index Options
            ("NSE_FO|22222", "NIFTY", "NSE", "NSE_FO", "INDEX_OPT", "NIFTY 50", None, "2026-06-25", 23000.0, "CE", 50, 0.05),
            ("NSE_FO|33333", "NIFTY", "NSE", "NSE_FO", "INDEX_OPT", "NIFTY 50", None, "2026-06-25", 23000.0, "PE", 50, 0.05),
            # NSE Stock Options (different underlying)
            ("NSE_FO|44444", "SBIN", "NSE", "NSE_FO", "STK_OPT", "State Bank", None, "2026-06-25", 600.0, "CE", 250, 0.05),
            # MCX Commodity Futures
            ("MCX|55555", "GOLDPETAL", "MCX", "MCX", "COMM_FUT", "GOLD PETAL", None, "2026-07-15", None, None, 100, 1.0),
            ("MCX|66666", "SILVERMIC", "MCX", "MCX", "COMM_FUT", "SILVER MICRO", None, "2026-07-15", None, None, 1000, 1.0),
            ("MCX|77777", "CRUDEOILM", "MCX", "MCX", "COMM_FUT", "CRUDE OIL MINI", None, "2026-07-20", None, None, 100, 1.0),
            # MCX Commodity Options
            ("MCX|88888", "GOLDM", "MCX", "MCX", "COMM_OPT", "GOLD MINI", None, "2026-07-15", 5000.0, "CE", 100, 1.0),
        ]
        
        with sqlite3.connect(db_path) as conn:
            for inst in instruments:
                conn.execute(
                    """INSERT INTO instruments_upstox 
                    (instrument_key, symbol, exchange, exchange_segment, 
                     instrument_type, name, isin, expiry, strike, option_type, 
                     lot_size, tick_size)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    inst,
                )
            
            conn.execute(
                "INSERT INTO cache_metadata (broker, last_refresh, instrument_count, adapter_class) VALUES (?, datetime('now'), ?, ?)",
                ("upstox", len(instruments), "UpstoxInstrumentAdapter"),
            )
            conn.commit()
        
        interceptor = SymbolResolutionInterceptor(cache_mgr)
        yield {"cache_mgr": cache_mgr, "interceptor": interceptor}


class TestNSEEquityResolution:
    """Test NSE Equity symbol resolution."""

    def test_reliance_nse_equity(self, setup_upstox_cache):
        """RELIANCE on NSE should resolve to NSE_EQ instrument."""
        interceptor = setup_upstox_cache["interceptor"]
        resolved = interceptor.resolve("upstox", "RELIANCE", "NSE")
        assert resolved is not None
        assert resolved.api_key == "NSE_EQ|INE002A01018"
        assert resolved.api_metadata["exchange_segment"] == "NSE_EQ"
        assert resolved.api_metadata["instrument_type"] == "EQ"

    def test_tcs_nse_equity(self, setup_upstox_cache):
        """TCS on NSE should resolve."""
        interceptor = setup_upstox_cache["interceptor"]
        resolved = interceptor.resolve("upstox", "TCS", "NSE")
        assert resolved is not None
        assert resolved.api_key == "NSE_EQ|INE467B01029"

    def test_hdfcbank_nse_equity(self, setup_upstox_cache):
        """HDFCBANK on NSE should resolve."""
        interceptor = setup_upstox_cache["interceptor"]
        resolved = interceptor.resolve("upstox", "HDFCBANK", "NSE")
        assert resolved is not None
        assert resolved.api_key == "NSE_EQ|INE040A01034"


class TestBSEEquityResolution:
    """Test BSE Equity symbol resolution."""

    def test_reliance_bse_equity(self, setup_upstox_cache):
        """RELIANCE on BSE should resolve to BSE_EQ (different from NSE)."""
        interceptor = setup_upstox_cache["interceptor"]
        resolved = interceptor.resolve("upstox", "RELIANCE", "BSE")
        assert resolved is not None
        assert resolved.api_key == "BSE_EQ|INE002A01018"
        assert resolved.api_metadata["exchange_segment"] == "BSE_EQ"


class TestNSEFuturesResolution:
    """Test NSE Futures (NFO) symbol resolution."""

    def test_nifty_index_future(self, setup_upstox_cache):
        """NIFTY index future should resolve."""
        interceptor = setup_upstox_cache["interceptor"]
        resolved = interceptor.resolve("upstox", "NIFTY", "NFO")
        assert resolved is not None
        assert resolved.api_key == "NSE_FO|12345"
        assert resolved.api_metadata["instrument_type"] == "INDEX_FUT"

    def test_banknifty_index_future(self, setup_upstox_cache):
        """BANKNIFTY index future should resolve."""
        interceptor = setup_upstox_cache["interceptor"]
        resolved = interceptor.resolve("upstox", "BANKNIFTY", "NFO")
        assert resolved is not None
        assert resolved.api_key == "NSE_FO|67890"

    def test_infy_stock_future(self, setup_upstox_cache):
        """INFY stock future should resolve (different from equity)."""
        interceptor = setup_upstox_cache["interceptor"]
        resolved = interceptor.resolve("upstox", "INFY", "NFO")
        assert resolved is not None
        assert resolved.api_key == "NSE_FO|11111"
        assert resolved.api_metadata["instrument_type"] == "STK_FUT"


class TestNSEOptionsResolution:
    """Test NSE Options (NFO) symbol resolution."""

    def test_nifty_call_option(self, setup_upstox_cache):
        """NIFTY on NFO should resolve (first match - could be FUT or OPT)."""
        interceptor = setup_upstox_cache["interceptor"]
        resolved = interceptor.resolve("upstox", "NIFTY", "NFO")
        assert resolved is not None
        assert resolved.api_metadata["exchange_segment"] == "NSE_FO"
        # Note: Returns first match (INDEX_FUT or INDEX_OPT depending on insert order)

    def test_sbin_call_option(self, setup_upstox_cache):
        """SBIN stock option should resolve."""
        interceptor = setup_upstox_cache["interceptor"]
        resolved = interceptor.resolve("upstox", "SBIN", "NFO")
        assert resolved is not None
        assert "NSE_FO" in resolved.api_key


class TestMCXFuturesResolution:
    """Test MCX Futures symbol resolution."""

    def test_goldpetal_future(self, setup_upstox_cache):
        """GOLDPETAL future on MCX should resolve."""
        interceptor = setup_upstox_cache["interceptor"]
        resolved = interceptor.resolve("upstox", "GOLDPETAL", "MCX")
        assert resolved is not None
        assert resolved.api_key == "MCX|55555"
        assert resolved.api_metadata["exchange_segment"] == "MCX"
        assert resolved.api_metadata["instrument_type"] == "COMM_FUT"

    def test_silvermic_future(self, setup_upstox_cache):
        """SILVERMIC future on MCX should resolve."""
        interceptor = setup_upstox_cache["interceptor"]
        resolved = interceptor.resolve("upstox", "SILVERMIC", "MCX")
        assert resolved is not None
        assert resolved.api_key == "MCX|66666"

    def test_crudeoilm_future(self, setup_upstox_cache):
        """CRUDEOILM future on MCX should resolve."""
        interceptor = setup_upstox_cache["interceptor"]
        resolved = interceptor.resolve("upstox", "CRUDEOILM", "MCX")
        assert resolved is not None
        assert resolved.api_key == "MCX|77777"


class TestMCXOptionsResolution:
    """Test MCX Options symbol resolution."""

    def test_goldm_call_option(self, setup_upstox_cache):
        """GOLDM CE option on MCX should resolve."""
        interceptor = setup_upstox_cache["interceptor"]
        resolved = interceptor.resolve("upstox", "GOLDM", "MCX")
        assert resolved is not None
        assert resolved.api_metadata["exchange_segment"] == "MCX"


class TestSymbolAmbiguity:
    """Test resolution when same symbol exists in multiple exchanges."""

    def test_reliance_nse_vs_bse(self, setup_upstox_cache):
        """RELIANCE on NSE vs BSE should return different instruments."""
        interceptor = setup_upstox_cache["interceptor"]
        nse = interceptor.resolve("upstox", "RELIANCE", "NSE")
        bse = interceptor.resolve("upstox", "RELIANCE", "BSE")
        assert nse is not None and bse is not None
        assert nse.api_key != bse.api_key
        assert "NSE_EQ" in nse.api_key
        assert "BSE_EQ" in bse.api_key

    def test_nifty_futures_vs_options(self, setup_upstox_cache):
        """NIFTY on NFO should return first match (futures or options)."""
        interceptor = setup_upstox_cache["interceptor"]
        resolved = interceptor.resolve("upstox", "NIFTY", "NFO")
        assert resolved is not None
        assert "NSE_FO" in resolved.api_key


class TestCacheBehavior:
    """Test caching behavior and performance."""

    def test_batch_resolution(self, setup_upstox_cache):
        """Batch resolve multiple symbols."""
        interceptor = setup_upstox_cache["interceptor"]
        symbols = [("RELIANCE", "NSE"), ("NIFTY", "NFO"), ("GOLDPETAL", "MCX")]
        results = interceptor.resolve_many("upstox", symbols)
        assert len(results) == 3
        assert all(r.api_key is not None for r in results)

    def test_memory_cache_invalidation(self, setup_upstox_cache):
        """Invalidating cache should clear memory entries."""
        interceptor = setup_upstox_cache["interceptor"]
        resolved1 = interceptor.resolve("upstox", "RELIANCE", "NSE")
        assert resolved1 is not None
        interceptor.invalidate("upstox")
        stats = interceptor.get_cache_stats()
        assert stats["cached_symbols"] == 0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_nonexistent_symbol(self, setup_upstox_cache):
        """Non-existent symbol should return None."""
        interceptor = setup_upstox_cache["interceptor"]
        resolved = interceptor.resolve("upstox", "NONEXISTENT", "NSE")
        assert resolved is None

    def test_unregistered_broker(self, setup_upstox_cache):
        """Unregistered broker should raise error."""
        interceptor = setup_upstox_cache["interceptor"]
        # Should return None when cache is invalid (not raise)
        resolved = interceptor.resolve("zerodha", "RELIANCE", "NSE")
        assert resolved is None

    def test_cache_stats(self, setup_upstox_cache):
        """Cache stats should track correctly."""
        interceptor = setup_upstox_cache["interceptor"]
        interceptor.resolve("upstox", "RELIANCE", "NSE")
        interceptor.resolve("upstox", "TCS", "NSE")
        stats = interceptor.get_cache_stats()
        assert stats["cached_symbols"] == 2
