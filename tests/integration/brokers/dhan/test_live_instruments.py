"""Live integration tests for Dhan instrument and search endpoints.

Tests search() and load_instruments() against the live Dhan API.

These tests require a valid .env.local with DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))


pytestmark = [pytest.mark.dhan, pytest.mark.off_market_safe, pytest.mark.regression]
from brokers.dhan.wire import DhanBrokerGateway

# ---------------------------------------------------------------------------
# Skip guard — only run when .env.local has valid credentials
# ---------------------------------------------------------------------------

ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env.local"
_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=True)
    _live_env_loaded = bool(os.environ.get("DHAN_CLIENT_ID"))


@pytest.mark.skipif(not _live_env_loaded, reason=".env.local with DHAN_CLIENT_ID required")
class TestLiveInstruments:
    """Instrument and search endpoint tests against live Dhan API."""

    def test_search_known_symbol_reliance(self, gateway: DhanBrokerGateway):
        """search() for RELIANCE should return results."""
        results = gateway.search("RELIANCE")
        assert isinstance(results, list)
        assert len(results) > 0
        # Verify result structure
        first = results[0]
        assert "symbol" in first
        assert "exchange" in first

    def test_search_known_symbol_nifty(self, gateway: DhanBrokerGateway):
        """search() for NIFTY should return index results."""
        results = gateway.search("NIFTY")
        assert isinstance(results, list)
        assert len(results) > 0
        # Should find NIFTY index
        symbols = [r["symbol"] for r in results]
        assert any("NIFTY" in s for s in symbols)

    def test_search_known_symbol_tcs(self, gateway: DhanBrokerGateway):
        """search() for TCS should return results."""
        results = gateway.search("TCS")
        assert isinstance(results, list)
        assert len(results) > 0

    def test_search_returns_correct_fields(self, gateway: DhanBrokerGateway):
        """search() results should have symbol, exchange, type, security_id, name."""
        results = gateway.search("RELIANCE")
        if results:
            first = results[0]
            required_fields = ["symbol", "exchange", "type"]
            for field in required_fields:
                assert field in first, f"Search result missing field: {field}"

    def test_search_partial_match(self, gateway: DhanBrokerGateway):
        """search() with partial symbol should return matches."""
        results = gateway.search("REL")
        assert isinstance(results, list)
        # Should find RELIANCE and potentially others
        assert len(results) > 0

    def test_search_limit_20_results(self, gateway: DhanBrokerGateway):
        """search() should limit results to 20."""
        results = gateway.search("INF")  # Common prefix
        assert isinstance(results, list)
        assert len(results) <= 20

    def test_load_instruments_success(self, gateway: DhanBrokerGateway):
        """load_instruments() should load instruments successfully."""
        # Gateway fixture already loads instruments, verify they're loaded
        desc = gateway.describe()
        assert desc["instruments_loaded"] is True
        assert desc["instrument_count"] > 0

    def test_instrument_count_large(self, gateway: DhanBrokerGateway):
        """Instrument count should be > 100,000 for full Dhan universe."""
        desc = gateway.describe()
        count = desc["instrument_count"]
        assert count > 100000, f"Expected >100k instruments, got {count}"

    def test_instrument_service_is_loaded(self, gateway: DhanBrokerGateway):
        """Broker-internal instrument service must be loaded and queryable."""
        svc = gateway._conn.instruments
        assert svc.is_loaded() is True
        assert svc.stats()["total"] > 0
        # Canonical resolve has no wire id on the carrier
        resolved = svc.resolve("RELIANCE", "NSE")
        assert resolved.symbol
        assert not hasattr(resolved, "security_id") or getattr(resolved, "security_id", None) in (
            None,
            "",
        )

    def test_resolve_ref_stays_internal(self, gateway: DhanBrokerGateway):
        """resolve_ref returns wire segment+security_id for connection use only."""
        ref = gateway._conn.instruments.resolve_dhan_ref("RELIANCE", "NSE")
        assert ref.security_id.isdigit()
        assert ref.exchange_segment
        # Gateway search / describe must not be the only path — wire ref works
        wire = gateway._conn.instruments.resolve_ref("RELIANCE", "NSE")
        assert wire.require("security_id") == ref.security_id_str()
        assert wire.require("exchange_segment") == ref.exchange_segment

    def test_gateway_stream_depth_delegate_to_connection(self, gateway: DhanBrokerGateway):
        """Gateway stream/depth_20/depth_200 must not compute security_id themselves."""
        import inspect

        for name in ("stream", "depth_20", "depth_200"):
            src = inspect.getsource(getattr(gateway.__class__, name))
            assert "EXCHANGE_TO_SEGMENT" not in src, f"gateway.{name} still maps segments"
            assert "int(inst.security_id)" not in src, f"gateway.{name} still casts security_id"
            assert "instruments.resolve(" not in src, f"gateway.{name} still resolves wire ids"
            assert "subscribe_" in src, f"gateway.{name} should delegate to connection.subscribe_*"

    def test_search_case_insensitive(self, gateway: DhanBrokerGateway):
        """search() should be case-insensitive."""
        results_upper = gateway.search("RELIANCE")
        results_lower = gateway.search("reliance")
        # Both should return results
        assert len(results_upper) > 0
        assert len(results_lower) > 0
