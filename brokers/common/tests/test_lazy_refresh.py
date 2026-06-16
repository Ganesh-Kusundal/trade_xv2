"""Tests for transparent lazy refresh functionality."""

import sqlite3
import tempfile
import time
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest

from brokers.common.instrument_cache import InstrumentCacheManager
from brokers.upstox.instruments.cache_adapter import UpstoxInstrumentAdapter
from brokers.upstox.instruments.definition import UpstoxInstrumentDefinition


@pytest.fixture
def setup_cache_with_loader():
    """Create cache with a mock loader."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        
        cache_mgr = InstrumentCacheManager(db_path=db_path)
        adapter = UpstoxInstrumentAdapter(db_path=db_path)
        cache_mgr.register_adapter(adapter)
        
        # Create REAL instrument objects (not Mocks)
        mock_instruments = [
            UpstoxInstrumentDefinition(
                instrument_key="NSE_EQ|INE002A01018",
                symbol="RELIANCE",
                exchange="NSE",
                exchange_segment="NSE_EQ",
                instrument_type="EQ",
                name="Reliance Industries",
                isin="INE002A01018",
                trading_symbol="RELIANCE",
                expiry=None,
                strike=None,
                option_type=None,
                underlying_symbol=None,
                lot_size=1,
                tick_size=0.05,
            ),
            UpstoxInstrumentDefinition(
                instrument_key="NSE_EQ|INE467B01029",
                symbol="TCS",
                exchange="NSE",
                exchange_segment="NSE_EQ",
                instrument_type="EQ",
                name="Tata Consultancy",
                isin="INE467B01029",
                trading_symbol="TCS",
                expiry=None,
                strike=None,
                option_type=None,
                underlying_symbol=None,
                lot_size=1,
                tick_size=0.05,
            ),
        ]
        
        loader_fn = Mock(return_value=mock_instruments)
        cache_mgr.register_loader("upstox", loader_fn)
        
        yield {
            "cache_mgr": cache_mgr,
            "loader_fn": loader_fn,
            "db_path": db_path,
        }


class TestLazyRefresh:
    """Test transparent lazy refresh on first call."""

    def test_refresh_on_expired_cache(self, setup_cache_with_loader):
        """First call with expired cache should trigger refresh."""
        cache_mgr = setup_cache_with_loader["cache_mgr"]
        loader_fn = setup_cache_with_loader["loader_fn"]
        
        # Verify cache is invalid (empty)
        assert not cache_mgr.is_cache_valid("upstox")
        
        # Resolve symbol - should trigger lazy refresh
        resolved = cache_mgr.resolve_symbol("upstox", "RELIANCE", "NSE")
        
        # Verify loader was called
        loader_fn.assert_called_once()
        
        # Verify resolution works after refresh
        assert resolved is not None
        assert resolved["instrument_key"] == "NSE_EQ|INE002A01018"
        assert resolved["symbol"] == "RELIANCE"

    def test_no_refresh_on_valid_cache(self, setup_cache_with_loader):
        """Second call should use cache without refresh."""
        cache_mgr = setup_cache_with_loader["cache_mgr"]
        loader_fn = setup_cache_with_loader["loader_fn"]
        
        # First call triggers refresh
        cache_mgr.resolve_symbol("upstox", "RELIANCE", "NSE")
        assert loader_fn.call_count == 1
        
        # Second call should NOT trigger refresh
        cache_mgr.resolve_symbol("upstox", "TCS", "NSE")
        assert loader_fn.call_count == 1  # Still 1, not 2

    def test_loader_failure_graceful_degradation(self, setup_cache_with_loader):
        """Loader failure should not raise exception."""
        cache_mgr = setup_cache_with_loader["cache_mgr"]
        loader_fn = setup_cache_with_loader["loader_fn"]
        
        # Make loader raise exception
        loader_fn.side_effect = Exception("Network error")
        
        # Should not raise, just return None
        resolved = cache_mgr.resolve_symbol("upstox", "RELIANCE", "NSE")
        assert resolved is None

    def test_loader_returns_empty_list(self, setup_cache_with_loader):
        """Empty loader result should not cache anything."""
        cache_mgr = setup_cache_with_loader["cache_mgr"]
        loader_fn = setup_cache_with_loader["loader_fn"]
        
        # Make loader return empty list
        loader_fn.return_value = []
        
        # Resolve should return None (no instruments cached)
        resolved = cache_mgr.resolve_symbol("upstox", "RELIANCE", "NSE")
        assert resolved is None
        assert cache_mgr.get_instrument_count("upstox") == 0

    def test_no_loader_registered(self):
        """Should gracefully handle missing loader."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            cache_mgr = InstrumentCacheManager(db_path=db_path)
            adapter = UpstoxInstrumentAdapter(db_path=db_path)
            cache_mgr.register_adapter(adapter)
            # NO loader registered
            
            # Should not raise, just return None
            resolved = cache_mgr.resolve_symbol("upstox", "RELIANCE", "NSE")
            assert resolved is None

    def test_concurrent_calls_single_refresh(self, setup_cache_with_loader):
        """Concurrent calls should only trigger one refresh."""
        cache_mgr = setup_cache_with_loader["cache_mgr"]
        loader_fn = setup_cache_with_loader["loader_fn"]
        
        call_count_lock = threading.Lock()
        actual_calls = [0]
        
        # Wrap loader to count calls safely
        original_return = loader_fn.return_value
        def tracked_loader():
            with call_count_lock:
                actual_calls[0] += 1
            time.sleep(0.05)  # Small delay to simulate work
            return original_return
        
        loader_fn.side_effect = tracked_loader
        
        # Launch 5 concurrent calls
        results = [None] * 5
        def resolve(idx):
            results[idx] = cache_mgr.resolve_symbol("upstox", "RELIANCE", "NSE")
        
        threads = [threading.Thread(target=resolve, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Loader should be called only once (not 5 times)
        assert actual_calls[0] == 1, f"Expected 1 call, got {actual_calls[0]}"
        
        # All calls should succeed
        assert all(r is not None for r in results), "All resolutions should succeed"
