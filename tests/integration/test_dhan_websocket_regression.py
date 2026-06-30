"""Regression test suite for Dhan WebSocket market feed and depth feeds.

Tests:
1. Gateway stream(): Receives ticks via gateway.stream()
2. Gateway depth_20(): Returns MarketDepth with domain types
3. Depth-20 WebSocket: Receives depth updates via callback
4. Zero-LTP filtering: Previous Close packets don't generate ticks
5. Domain type compliance: All returns are proper domain entities

Requires live Dhan credentials in .env.local.
Run with: pytest tests/integration/test_dhan_websocket_regression.py -v -s
"""

from __future__ import annotations

import contextlib
import time
from decimal import Decimal

import pytest

from domain import Balance, DepthLevel, MarketDepth, Quote

# Skip entire module if no Dhan credentials
pytestmark = pytest.mark.skipif(
    not pytest.importorskip("dhanhq", reason="dhanhq not installed"),
    reason="dhanhq not installed",
)


@pytest.fixture(scope="module")
def gateway():
    """Bootstrap a live Dhan gateway for the test module."""
    from cli.services.broker_registry import bootstrap_gateway

    result = bootstrap_gateway("dhan")
    if not result.ok:
        pytest.skip(f"Dhan gateway not available: {result.error}")
    gw = result.gateway
    yield gw
    with contextlib.suppress(Exception):
        gw.close()


def _wait_for_ticks(collector: list, min_count: int = 1, timeout: float = 10.0) -> bool:
    """Wait until collector has at least min_count items or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline and len(collector) < min_count:
        time.sleep(0.5)
    return len(collector) >= min_count


def _is_rate_limited(exc_str: str) -> bool:
    """Check if an exception string indicates HTTP 429 rate limiting."""
    return "429" in exc_str or "rate limit" in exc_str.lower()


# ── Test 1: Gateway stream() ───────────────────────────────────────────────────


class TestGatewayStream:
    """Verify gateway.stream() receives ticks via DhanMarketFeed wrapper."""

    def test_stream_receives_ticks(self, gateway):
        """gateway.stream() must deliver ticks to on_tick callback."""
        ticks: list[Quote] = []

        def on_tick(quote: Quote):
            ticks.append(quote)

        try:
            feed = gateway.stream("TCS", "NSE", mode="LTP", on_tick=on_tick)
            received = _wait_for_ticks(ticks, min_count=1, timeout=10)
            with contextlib.suppress(Exception):
                feed.stop(timeout_seconds=3)
            assert received, "gateway.stream() must deliver at least 1 tick within 10s"
        except Exception as exc:
            if _is_rate_limited(str(exc)):
                pytest.skip(f"Rate limited by Dhan: {exc}")
            raise

    def test_stream_ticks_have_positive_ltp(self, gateway):
        """All ticks from gateway.stream() must have positive LTP (no zero-LTP)."""
        ticks: list[Quote] = []

        def on_tick(quote: Quote):
            ticks.append(quote)

        try:
            feed = gateway.stream("TCS", "NSE", mode="LTP", on_tick=on_tick)
            _wait_for_ticks(ticks, min_count=2, timeout=10)
            with contextlib.suppress(Exception):
                feed.stop(timeout_seconds=3)
        except Exception as exc:
            if _is_rate_limited(str(exc)):
                pytest.skip(f"Rate limited by Dhan: {exc}")
            raise

        assert len(ticks) >= 1, "Must receive at least 1 tick"
        for tick in ticks:
            assert isinstance(tick, Quote), f"Expected Quote, got {type(tick)}"
            assert tick.ltp > 0, f"LTP must be positive, got {tick.ltp}"

    def test_stream_returns_domain_quote(self, gateway):
        """on_tick callback must receive Quote domain objects."""
        received_types: list[type] = []

        def on_tick(quote):
            received_types.append(type(quote))

        try:
            feed = gateway.stream("TCS", "NSE", mode="LTP", on_tick=on_tick)
            _wait_for_ticks(received_types, min_count=1, timeout=10)
            with contextlib.suppress(Exception):
                feed.stop(timeout_seconds=3)
        except Exception as exc:
            if _is_rate_limited(str(exc)):
                pytest.skip(f"Rate limited by Dhan: {exc}")
            raise

        assert len(received_types) >= 1
        assert received_types[0] is Quote, f"Expected Quote, got {received_types[0]}"


# ── Test 2: Gateway depth_20() ─────────────────────────────────────────────────


class TestGatewayDepth20:
    """Verify gateway.depth_20() returns proper MarketDepth domain objects."""

    def test_depth_20_returns_market_depth(self, gateway):
        """depth_20() must return a MarketDepth instance."""
        depth = gateway.depth_20("TCS", "NSE")
        assert isinstance(depth, MarketDepth), f"Expected MarketDepth, got {type(depth)}"

    def test_depth_20_has_bids(self, gateway):
        """depth_20() must return at least some bid levels."""
        depth = gateway.depth_20("TCS", "NSE")
        assert len(depth.bids) > 0, "depth_20() must have at least 1 bid level"

    def test_depth_20_bids_are_depth_levels(self, gateway):
        """All bid levels must be DepthLevel domain objects."""
        depth = gateway.depth_20("TCS", "NSE")
        for level in depth.bids:
            assert isinstance(level, DepthLevel), f"Expected DepthLevel, got {type(level)}"
            assert level.price > 0, f"Bid price must be positive, got {level.price}"
            assert level.quantity > 0, f"Bid quantity must be positive, got {level.quantity}"

    def test_depth_20_websocket_receives_updates(self, gateway):
        """depth_20() WebSocket must deliver depth updates via callback."""
        updates: list[MarketDepth] = []

        def on_depth(depth: MarketDepth):
            updates.append(depth)

        try:
            gateway.depth_20("TCS", "NSE", on_depth=on_depth)
            _wait_for_ticks(updates, min_count=1, timeout=10)
        except Exception as exc:
            if _is_rate_limited(str(exc)):
                pytest.skip(f"Rate limited by Dhan: {exc}")
            raise
        finally:
            with contextlib.suppress(Exception):
                feed = gateway._conn.depth_20_feed
                if feed:
                    feed.stop(timeout_seconds=3)

        assert len(updates) >= 1, "depth_20 WebSocket must deliver at least 1 update"
        for update in updates:
            assert isinstance(update, MarketDepth)
            assert update.depth_type == "DEPTH_20"
            assert len(update.bids) > 0, "WebSocket depth must have bid levels"


# ── Test 3: Zero-LTP Filtering ─────────────────────────────────────────────────


class TestZeroLTPFiltering:
    """Verify Previous Close / OI / Status packets don't generate zero-LTP ticks."""

    def test_no_zero_ltp_ticks(self, gateway):
        """gateway.stream() must NOT deliver ticks with ltp=0."""
        ticks: list[Quote] = []

        def on_tick(quote: Quote):
            ticks.append(quote)

        try:
            feed = gateway.stream("TCS", "NSE", mode="LTP", on_tick=on_tick)
            _wait_for_ticks(ticks, min_count=2, timeout=10)
            with contextlib.suppress(Exception):
                feed.stop(timeout_seconds=3)
        except Exception as exc:
            if _is_rate_limited(str(exc)):
                pytest.skip(f"Rate limited by Dhan: {exc}")
            raise

        assert len(ticks) >= 1, "Must receive at least 1 tick"
        zero_ltp_ticks = [t for t in ticks if t.ltp == 0]
        assert len(zero_ltp_ticks) == 0, (
            f"Found {len(zero_ltp_ticks)} zero-LTP ticks — "
            "Previous Close packets must not generate ticks"
        )


# ── Test 4: Domain Type Compliance ─────────────────────────────────────────────


class TestDomainTypeCompliance:
    """Verify all gateway methods return proper domain entities."""

    def test_ltp_returns_decimal(self, gateway):
        """ltp() must return a Decimal."""
        ltp = gateway.ltp("TCS", "NSE")
        assert isinstance(ltp, Decimal), f"Expected Decimal, got {type(ltp)}"
        assert ltp > 0, f"LTP must be positive, got {ltp}"

    def test_quote_returns_quote(self, gateway):
        """quote() must return a Quote domain object."""
        q = gateway.quote("TCS", "NSE")
        assert isinstance(q, Quote), f"Expected Quote, got {type(q)}"
        assert q.ltp > 0, f"Quote LTP must be positive, got {q.ltp}"

    def test_depth_returns_market_depth(self, gateway):
        """depth() must return a MarketDepth domain object."""
        d = gateway.depth("TCS", "NSE")
        assert isinstance(d, MarketDepth), f"Expected MarketDepth, got {type(d)}"

    def test_balance_returns_balance(self, gateway):
        """funds() must return a Balance domain object."""
        bal = gateway.funds()
        assert isinstance(bal, Balance), f"Expected Balance, got {type(bal)}"
