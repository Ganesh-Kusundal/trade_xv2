#!/usr/bin/env python3
"""Diagnostic script: Root cause analysis for Dhan WebSocket market feed + depth_20.

Tests:
1. SDK direct: Connect to Dhan WebSocket SDK directly, subscribe to TCS, check if ticks arrive
2. Gateway stream(): Test gateway.stream() for TCS on NSE in LTP/QUOTE/FULL modes
3. Gateway depth_20(): Test gateway.depth_20() for TCS on NSE
4. Depth-20 WebSocket: Test depth_20 feed for TCS on NSE

Uses project venv and gateway.
"""

from __future__ import annotations

import contextlib
import logging
import sys
import threading
import time
from decimal import Decimal
from pathlib import Path

# Ensure project root is in path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("diag")


def section(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


# ── Test 1: SDK Direct ─────────────────────────────────────────────────────────

def test_sdk_direct(client_id: str, access_token: str, security_id: str) -> bool:
    """Test Dhan SDK MarketFeed directly — bypass our wrapper entirely."""
    section("TEST 1: SDK Direct — MarketFeed with TCS (NSE_EQ)")

    from dhanhq.marketfeed import MarketFeed

    ticks_received: list[dict] = []
    connect_called = False
    error_msgs: list[str] = []

    def on_connect(feed):
        nonlocal connect_called
        connect_called = True
        log.info("SDK on_connect fired")

    def on_message(feed, data):
        ticks_received.append(data)
        if len(ticks_received) <= 3:
            log.info("SDK tick #%d: %s", len(ticks_received), data)

    def on_error(feed, exc):
        error_msgs.append(str(exc))
        log.error("SDK on_error: %s", exc)

    def on_close(feed):
        log.info("SDK on_close fired")

    # Subscribe to TCS on NSE_EQ in Ticker mode (RequestCode=15)
    instruments = [(1, security_id, 15)]  # 1=NSE, security_id, 15=Ticker

    log.info("Creating MarketFeed with instruments=%s", instruments)
    feed = MarketFeed(
        dhan_context=_make_context(client_id, access_token),
        instruments=instruments,
        version='v2',
        on_connect=on_connect,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    # Run in a thread for 10 seconds
    t = threading.Thread(target=feed.run, daemon=True)
    t.start()

    # Wait for ticks
    for _i in range(10):
        time.sleep(1)
        if ticks_received:
            log.info("Received %d ticks so far...", len(ticks_received))
            if len(ticks_received) >= 3:
                break

    # Stop
    feed.close_connection()
    t.join(timeout=3)

    log.info("SDK Direct result: ticks=%d, connected=%s, errors=%d",
             len(ticks_received), connect_called, len(error_msgs))

    if error_msgs:
        log.error("Errors: %s", error_msgs[:3])

    return len(ticks_received) > 0


# ── Test 2: Gateway stream() ───────────────────────────────────────────────────

def test_gateway_stream(gw, symbol: str = "TCS", exchange: str = "NSE") -> bool:
    """Test gateway.stream() for TCS in LTP mode."""
    section(f"TEST 2: Gateway stream() — {symbol} on {exchange}")

    ticks: list = []

    def on_tick(quote):
        ticks.append(quote)
        if len(ticks) <= 3:
            log.info("Gateway tick #%d: %s", len(ticks), quote)

    log.info("Calling gw.stream('%s', '%s', mode='LTP', on_tick=...)", symbol, exchange)
    feed = gw.stream(symbol, exchange, mode="LTP", on_tick=on_tick)
    log.info("stream() returned feed=%s, is_connected=%s", type(feed).__name__, feed.is_connected)

    # Wait for ticks
    for _i in range(10):
        time.sleep(1)
        if ticks:
            log.info("Received %d ticks so far...", len(ticks))
            if len(ticks) >= 3:
                break

    # Check health
    try:
        health = feed.health()
        log.info("Feed health: state=%s, detail=%s, metrics=%s",
                 health.state.value, health.detail, health.metrics)
    except Exception as exc:
        log.warning("health() failed: %s", exc)

    log.info("Gateway stream result: ticks=%d", len(ticks))

    # Stop
    with contextlib.suppress(Exception):
        feed.stop(timeout_seconds=3)

    return len(ticks) > 0


# ── Test 3: Gateway depth_20() ─────────────────────────────────────────────────

def test_gateway_depth_20(gw, symbol: str = "TCS", exchange: str = "NSE") -> bool:
    """Test gateway.depth_20() for TCS."""
    section(f"TEST 3: Gateway depth_20() — {symbol} on {exchange}")

    log.info("Calling gw.depth_20('%s', '%s')", symbol, exchange)
    try:
        depth = gw.depth_20(symbol, exchange)
        log.info("depth_20 result: type=%s, bids=%d, asks=%d",
                 depth.depth_type, len(depth.bids), len(depth.asks))
        if depth.bids:
            log.info("  Best bid: price=%s, qty=%s", depth.bids[0].price, depth.bids[0].quantity)
        if depth.asks:
            log.info("  Best ask: price=%s, qty=%s", depth.asks[0].price, depth.asks[0].quantity)
        return len(depth.bids) > 0 or len(depth.asks) > 0
    except Exception as exc:
        log.error("depth_20 failed: %s", exc)
        return False


# ── Test 4: Depth-20 WebSocket feed directly ───────────────────────────────────

def test_depth_20_feed(gw, symbol: str = "TCS", exchange: str = "NSE") -> bool:
    """Test depth-20 WebSocket feed directly for TCS."""
    section(f"TEST 4: Depth-20 WebSocket Feed — {symbol} on {exchange}")

    depths: list = []

    def on_depth(depth):
        depths.append(depth)
        if len(depths) <= 3:
            log.info("Depth update #%d: bids=%d, asks=%d", len(depths), len(depth.bids), len(depth.asks))

    # Call depth_20 with callback
    log.info("Calling gw.depth_20('%s', '%s', on_depth=...)", symbol, exchange)
    try:
        depth = gw.depth_20(symbol, exchange, on_depth=on_depth)
        log.info("Initial depth: type=%s, bids=%d, asks=%d",
                 depth.depth_type, len(depth.bids), len(depth.asks))
    except Exception as exc:
        log.error("depth_20 initial call failed: %s", exc)
        return False

    # Wait for WebSocket depth updates
    for _i in range(10):
        time.sleep(1)
        if depths:
            log.info("Received %d depth updates so far...", len(depths))
            if len(depths) >= 3:
                break

    log.info("Depth-20 feed result: initial_bids=%d, updates=%d", len(depth.bids), len(depths))

    # Stop the feed
    try:
        feed = gw._conn.depth_20_feed
        if feed:
            feed.stop(timeout_seconds=3)
    except Exception:
        pass

    return len(depth.bids) > 0


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_context(client_id: str, access_token: str):
    """Create a minimal DhanContext for SDK."""
    from brokers.dhan.websocket._helpers import _DhanContext
    return _DhanContext(client_id, access_token=access_token)


def main():
    # Bootstrap gateway
    section("BOOTSTRAP")
    from cli.services.broker_registry import bootstrap_gateway

    result = bootstrap_gateway("dhan")
    if not result.ok:
        log.error("Bootstrap failed: %s", result.error)
        sys.exit(1)

    gw = result.gateway
    log.info("Bootstrap OK: status=%s", result.status.value)

    # Resolve TCS security_id
    inst = gw._conn.instruments.resolve("TCS", "NSE")
    security_id = inst.security_id
    log.info("TCS resolved: security_id=%s, exchange=%s", security_id, inst.exchange)

    # Get credentials for SDK direct test
    client_id = gw._conn._client.client_id
    access_token = gw._conn._client.access_token

    results = {}

    # Test 1: SDK Direct
    results["SDK Direct"] = test_sdk_direct(client_id, access_token, security_id)
    time.sleep(2)  # Cool down between tests

    # Test 2: Gateway stream()
    results["Gateway stream()"] = test_gateway_stream(gw, "TCS", "NSE")
    time.sleep(2)

    # Test 3: Gateway depth_20()
    results["Gateway depth_20()"] = test_gateway_depth_20(gw, "TCS", "NSE")
    time.sleep(2)

    # Test 4: Depth-20 WebSocket feed
    results["Depth-20 Feed"] = test_depth_20_feed(gw, "TCS", "NSE")

    # Summary
    section("SUMMARY")
    all_pass = True
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        log.info("  %s: %s", name, status)
        if not passed:
            all_pass = False

    if all_pass:
        log.info("ALL TESTS PASSED")
    else:
        log.warning("SOME TESTS FAILED")

    # Cleanup
    with contextlib.suppress(Exception):
        gw.close()


if __name__ == "__main__":
    main()
