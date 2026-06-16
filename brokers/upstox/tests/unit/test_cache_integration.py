"""Integration test for lazy refresh with real broker factory."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from brokers.common.instrument_cache import InstrumentCacheManager
from brokers.common.symbol_resolver import SymbolResolutionInterceptor
from brokers.upstox.instruments.cache_adapter import UpstoxInstrumentAdapter
from brokers.upstox.instruments.definition import UpstoxInstrumentDefinition


@pytest.fixture
def mock_broker():
    """Create a mock UpstoxBroker with instrument loader."""
    broker = Mock()
    
    # Create mock instruments
    instruments = [
        UpstoxInstrumentDefinition(
            instrument_key="NSE_EQ|INE002A01018",
            symbol="RELIANCE",
            exchange="NSE",
            exchange_segment="NSE_EQ",
            instrument_type="EQ",
            name="Reliance Industries",
            isin="INE002A01018",
            lot_size=1,
            tick_size=0.05,
        ),
        UpstoxInstrumentDefinition(
            instrument_key="NSE_FO|12345",
            symbol="NIFTY",
            exchange="NSE",
            exchange_segment="NSE_FO",
            instrument_type="INDEX_FUT",
            name="NIFTY 50",
            lot_size=50,
            tick_size=0.05,
            expiry="2026-06-25",
        ),
    ]
    
    # Mock the loader
    mock_loader = Mock()
    mock_loader.download = Mock(return_value=Path("/tmp/test.json.gz"))
    mock_loader.load = Mock(return_value=instruments)
    broker.instrument_loader = mock_loader
    
    return broker


def test_cache_setup_with_lazy_refresh(mock_broker):
    """Test that cache is set up correctly and lazy refresh works."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "instruments.db"
        
        # Set up cache (mimicking factory code)
        cache_mgr = InstrumentCacheManager(db_path=db_path)
        adapter = UpstoxInstrumentAdapter(db_path=db_path)
        cache_mgr.register_adapter(adapter)
        
        # Register loader
        def load_fn():
            return mock_broker.instrument_loader.load(Path("/tmp/test.json.gz"))
        
        cache_mgr.register_loader("upstox", load_fn)
        
        # Create interceptor
        interceptor = SymbolResolutionInterceptor(cache_mgr)
        
        # Verify cache is initially invalid
        assert not cache_mgr.is_cache_valid("upstox")
        
        # First call should trigger lazy refresh
        resolved = cache_mgr.resolve_symbol("upstox", "RELIANCE", "NSE")
        
        # Verify loader was called
        mock_broker.instrument_loader.load.assert_called_once()
        
        # Verify resolution works
        assert resolved is not None
        assert resolved["instrument_key"] == "NSE_EQ|INE002A01018"
        assert resolved["symbol"] == "RELIANCE"
        
        # Second call should NOT trigger reload
        cache_mgr.resolve_symbol("upstox", "NIFTY", "NFO")
        assert mock_broker.instrument_loader.load.call_count == 1


def test_cache_persists_across_instances(mock_broker):
    """Test that cache persists and can be loaded by new manager instance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "instruments.db"
        
        # First manager: populate cache
        cache_mgr1 = InstrumentCacheManager(db_path=db_path)
        adapter1 = UpstoxInstrumentAdapter(db_path=db_path)
        cache_mgr1.register_adapter(adapter1)
        
        def load_fn():
            return mock_broker.instrument_loader.load(Path("/tmp/test.json.gz"))
        
        cache_mgr1.register_loader("upstox", load_fn)
        
        # Trigger refresh
        cache_mgr1.resolve_symbol("upstox", "RELIANCE", "NSE")
        assert mock_broker.instrument_loader.load.call_count == 1
        
        # Second manager: should use existing cache (no reload)
        cache_mgr2 = InstrumentCacheManager(db_path=db_path)
        adapter2 = UpstoxInstrumentAdapter(db_path=db_path)
        cache_mgr2.register_adapter(adapter2)
        cache_mgr2.register_loader("upstox", load_fn)
        
        resolved = cache_mgr2.resolve_symbol("upstox", "RELIANCE", "NSE")
        
        # Should NOT call loader again (cache is valid)
        assert mock_broker.instrument_loader.load.call_count == 1
        assert resolved is not None
        assert resolved["symbol"] == "RELIANCE"
