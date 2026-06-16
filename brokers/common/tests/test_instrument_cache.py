"""Unit tests for InstrumentCacheManager."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from brokers.common.instrument_cache import (
    BrokerInstrumentAdapter,
    InstrumentCacheManager,
)


class MockInstrument:
    """Mock instrument for testing."""

    def __init__(self, symbol, exchange, instrument_key, api_key):
        self.symbol = symbol
        self.exchange = exchange
        self.instrument_key = instrument_key
        self.api_key = api_key


class MockAdapter(BrokerInstrumentAdapter):
    """Mock adapter for testing."""

    @property
    def broker_name(self) -> str:
        return "mock"

    @property
    def table_name(self) -> str:
        return "instruments_mock"

    def get_schema(self) -> str:
        return """
            CREATE TABLE IF NOT EXISTS instruments_mock (
                instrument_key TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                api_key TEXT NOT NULL
            )
        """

    def get_indexes(self) -> list[str]:
        return [
            "CREATE INDEX IF NOT EXISTS idx_mock_symbol ON instruments_mock(symbol, exchange)",
        ]

    def to_row(self, instrument: MockInstrument) -> dict:
        return {
            "instrument_key": instrument.instrument_key,
            "symbol": instrument.symbol,
            "exchange": instrument.exchange,
            "api_key": instrument.api_key,
        }

    def from_row(self, row: dict) -> MockInstrument:
        return MockInstrument(
            symbol=row["symbol"],
            exchange=row["exchange"],
            instrument_key=row["instrument_key"],
            api_key=row["api_key"],
        )

    def resolve_symbol(self, symbol: str, exchange: str) -> dict | None:
        import sqlite3

        with sqlite3.connect(":memory:") as conn:
            # This is a simplified version - real adapter would use the actual DB
            return None

    def build_api_key(self, row: dict) -> str:
        return row.get("api_key", "")

    def build_api_metadata(self, row: dict) -> dict:
        return {"exchange": row.get("exchange")}


@pytest.fixture
def cache_manager():
    """Create a cache manager with temp database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        manager = InstrumentCacheManager(db_path=db_path)
        yield manager


@pytest.fixture
def cache_with_adapter(cache_manager):
    """Cache manager with mock adapter registered."""
    adapter = MockAdapter()
    cache_manager.register_adapter(adapter)
    return cache_manager


class TestInstrumentCacheManager:
    """Test suite for InstrumentCacheManager."""

    def test_metadata_table_created(self, cache_manager):
        """Metadata table should be created on initialization."""
        import sqlite3

        with sqlite3.connect(cache_manager.db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='cache_metadata'"
            )
            assert cursor.fetchone() is not None

    def test_register_adapter_creates_table(self, cache_with_adapter):
        """Registering an adapter should create the broker table."""
        import sqlite3

        with sqlite3.connect(cache_with_adapter.db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='instruments_mock'"
            )
            assert cursor.fetchone() is not None

    def test_register_adapter_creates_indexes(self, cache_with_adapter):
        """Registering an adapter should create indexes."""
        import sqlite3

        with sqlite3.connect(cache_with_adapter.db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_mock_symbol'"
            )
            assert cursor.fetchone() is not None

    def test_cache_valid_when_empty(self, cache_manager):
        """Cache should be invalid when no data exists."""
        assert cache_manager.is_cache_valid("mock") is False

    def test_cache_valid_after_insert(self, cache_with_adapter):
        """Cache should be valid after inserting instruments."""
        instruments = [
            MockInstrument("RELIANCE", "NSE", "KEY1", "API1"),
            MockInstrument("TCS", "NSE", "KEY2", "API2"),
        ]
        cache_with_adapter.cache_instruments("mock", instruments)
        assert cache_with_adapter.is_cache_valid("mock") is True

    def test_get_instrument_count(self, cache_with_adapter):
        """Should return correct instrument count."""
        instruments = [
            MockInstrument("RELIANCE", "NSE", "KEY1", "API1"),
            MockInstrument("TCS", "NSE", "KEY2", "API2"),
        ]
        cache_with_adapter.cache_instruments("mock", instruments)
        assert cache_with_adapter.get_instrument_count("mock") == 2

    def test_cache_instruments_clears_old_data(self, cache_with_adapter):
        """Caching instruments should replace existing data."""
        # Insert first batch
        cache_with_adapter.cache_instruments(
            "mock",
            [MockInstrument("OLD", "NSE", "OLD1", "OLD_API")],
        )

        # Insert second batch
        cache_with_adapter.cache_instruments(
            "mock",
            [MockInstrument("NEW", "NSE", "NEW1", "NEW_API")],
        )

        # Should only have NEW
        assert cache_with_adapter.get_instrument_count("mock") == 1

    def test_delete_cache(self, cache_with_adapter):
        """Deleting cache should remove all data."""
        instruments = [MockInstrument("RELIANCE", "NSE", "KEY1", "API1")]
        cache_with_adapter.cache_instruments("mock", instruments)
        assert cache_with_adapter.get_instrument_count("mock") == 1

        cache_with_adapter.delete_cache("mock")
        assert cache_with_adapter.get_instrument_count("mock") == 0

    def test_search_by_prefix(self, cache_with_adapter):
        """Search should find instruments by symbol prefix."""
        instruments = [
            MockInstrument("RELIANCE", "NSE", "KEY1", "API1"),
            MockInstrument("RELIANCEIND", "NSE", "KEY2", "API2"),
            MockInstrument("TCS", "NSE", "KEY3", "API3"),
        ]
        cache_with_adapter.cache_instruments("mock", instruments)

        results = cache_with_adapter.search("mock", "REL")
        assert len(results) == 2
        assert all(r["symbol"].startswith("REL") for r in results)

    def test_search_with_exchange_filter(self, cache_with_adapter):
        """Search should filter by exchange."""
        instruments = [
            MockInstrument("RELIANCE", "NSE", "KEY1", "API1"),
            MockInstrument("RELIANCE", "BSE", "KEY2", "API2"),
        ]
        cache_with_adapter.cache_instruments("mock", instruments)

        results = cache_with_adapter.search("mock", "REL", exchange="NSE")
        assert len(results) == 1
        assert results[0]["exchange"] == "NSE"

    def test_search_limit(self, cache_with_adapter):
        """Search should respect limit."""
        instruments = [
            MockInstrument(f"STOCK{i}", "NSE", f"KEY{i}", f"API{i}")
            for i in range(100)
        ]
        cache_with_adapter.cache_instruments("mock", instruments)

        results = cache_with_adapter.search("mock", "STOCK", limit=10)
        assert len(results) == 10

    def test_get_adapter_raises_on_unknown_broker(self, cache_manager):
        """Should raise KeyError for unregistered broker."""
        with pytest.raises(KeyError, match="No adapter registered"):
            cache_manager.get_adapter("unknown")

    def test_bulk_insert_performance(self, cache_with_adapter):
        """Should handle bulk inserts efficiently."""
        import time

        instruments = [
            MockInstrument(f"STOCK{i}", "NSE", f"KEY{i}", f"API{i}")
            for i in range(10000)
        ]

        start = time.time()
        count = cache_with_adapter.cache_instruments("mock", instruments)
        elapsed = time.time() - start

        assert count == 10000
        assert elapsed < 5.0  # Should complete in under 5 seconds

    def test_cache_metadata_updated(self, cache_with_adapter):
        """Cache metadata should be updated with correct values."""
        instruments = [MockInstrument("RELIANCE", "NSE", "KEY1", "API1")]
        cache_with_adapter.cache_instruments("mock", instruments)

        import sqlite3

        with sqlite3.connect(cache_with_adapter.db_path) as conn:
            cursor = conn.execute(
                "SELECT broker, instrument_count, adapter_class FROM cache_metadata WHERE broker='mock'"
            )
            row = cursor.fetchone()
            assert row[0] == "mock"
            assert row[1] == 1
            assert row[2] == "MockAdapter"
