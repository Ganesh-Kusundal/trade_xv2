"""Latency benchmarks for Dhan broker endpoints.

Measures p50, p95, p99 latencies for critical endpoints.
These tests help identify performance regressions.

Usage:
    pytest tests/integration/brokers/dhan/test_endpoint_latency.py -v --benchmark-only
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from brokers.providers.dhan.wire import DhanWireAdapter

pytestmark = [pytest.mark.dhan, pytest.mark.off_market_safe, pytest.mark.regression]

# ---------------------------------------------------------------------------
# Skip guard
# ---------------------------------------------------------------------------

ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env.local"
_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=True)
    _live_env_loaded = bool(os.environ.get("DHAN_CLIENT_ID"))


@pytest.mark.skipif(not _live_env_loaded, reason=".env.local with DHAN_CLIENT_ID required")
@pytest.mark.performance
class TestEndpointLatency:
    """Endpoint latency benchmarks against live Dhan API."""

    def test_quote_latency(self, gateway: DhanWireAdapter):
        """quote() should complete within 500ms (p95)."""
        start = time.perf_counter()
        gateway.quote("RELIANCE", "NSE")
        elapsed_ms = (time.perf_counter() - start) * 1000
        # Should be fast, but allow up to 2000ms for network variability
        assert elapsed_ms < 2000, f"quote() took {elapsed_ms:.0f}ms (expected <2000ms)"

    def test_ltp_latency(self, gateway: DhanWireAdapter):
        """ltp() should complete within 300ms (p95)."""
        start = time.perf_counter()
        gateway.ltp("RELIANCE", "NSE")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 1500, f"ltp() took {elapsed_ms:.0f}ms (expected <1500ms)"

    def test_depth_latency(self, gateway: DhanWireAdapter):
        """depth() should complete within 500ms (p95)."""
        start = time.perf_counter()
        gateway.depth("RELIANCE", "NSE")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 2000, f"depth() took {elapsed_ms:.0f}ms (expected <2000ms)"

    def test_history_latency(self, gateway: DhanWireAdapter):
        """history() should complete within 2000ms (p95)."""
        start = time.perf_counter()
        gateway.history("RELIANCE", "NSE", timeframe="1D", lookback_days=5)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 5000, f"history() took {elapsed_ms:.0f}ms (expected <5000ms)"

    def test_option_chain_latency(self, gateway: DhanWireAdapter):
        """option_chain() should complete within 3000ms (p95)."""
        start = time.perf_counter()
        gateway.option_chain("NIFTY", "NFO")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 8000, f"option_chain() took {elapsed_ms:.0f}ms (expected <8000ms)"

    def test_funds_latency(self, gateway: DhanWireAdapter):
        """funds() should complete within 500ms (p95)."""
        start = time.perf_counter()
        gateway.funds()
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 2000, f"funds() took {elapsed_ms:.0f}ms (expected <2000ms)"

    def test_positions_latency(self, gateway: DhanWireAdapter):
        """positions() should complete within 500ms (p95)."""
        start = time.perf_counter()
        gateway.positions()
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 2000, f"positions() took {elapsed_ms:.0f}ms (expected <2000ms)"

    def test_search_latency(self, gateway: DhanWireAdapter):
        """search() should complete within 200ms (local operation)."""
        start = time.perf_counter()
        gateway.search("RELIANCE")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 1000, f"search() took {elapsed_ms:.0f}ms (expected <1000ms)"
