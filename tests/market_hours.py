"""Market hours detection and test skip helpers.

Provides utilities to skip live/real-API tests during off-market hours.
This prevents flaky test failures when exchanges are closed and
WebSocket connections cannot be established.

Usage in tests::

    from tests.market_hours import skip_off_market, is_market_open

    @skip_off_market
    def test_websocket_connects():
        ...

    def test_something():
        if not is_market_open():
            pytest.skip("Market is closed")
"""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta, timezone

import pytest

# IST = UTC+5:30
IST = timezone(timedelta(hours=5, minutes=30))

# NSE trading hours (Monday-Friday)
NSE_OPEN = time(9, 15)
NSE_CLOSE = time(15, 30)

# Allow environment variable override for CI
FORCE_MARKET_OPEN = os.environ.get("FORCE_MARKET_OPEN", "0") == "1"


def now_ist() -> datetime:
    """Get current time in IST."""
    return datetime.now(IST)


def is_market_open() -> bool:
    """Check if NSE market is currently open.

    Returns True if:
    - Current IST time is between 09:15 and 15:30
    - Today is a weekday (Mon-Fri)
    - FORCE_MARKET_OPEN=1 is set (for CI)

    Note: Does not check for exchange holidays.
    """
    if FORCE_MARKET_OPEN:
        return True

    now = now_ist()

    # Weekend check
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False

    # Time check
    market_time = now.time()
    return NSE_OPEN <= market_time <= NSE_CLOSE


def is_near_market_hours() -> bool:
    """Check if we're within 30 minutes of market hours.

    Useful for tests that need warm-up time before market opens.
    """
    if FORCE_MARKET_OPEN:
        return True

    now = now_ist()
    market_time = now.time()

    # Extend window by 30 minutes on each side
    early_open = time(max(0, NSE_OPEN.hour), max(0, NSE_OPEN.minute - 30))
    late_close = time(min(23, NSE_CLOSE.hour), min(59, NSE_CLOSE.minute + 30))

    return early_open <= market_time <= late_close


# ── Pytest skip decorators ────────────────────────────────────────────────


def skip_off_market(reason: str | None = None):
    """Skip test if market is closed.

    Usage::

        @skip_off_market
        def test_websocket():
            ...

        @skip_off_market(reason="needs live feed")
        def test_ticks():
            ...
    """
    msg = reason or "Market is closed (off-hours)"
    return pytest.mark.skipif(
        not is_market_open(),
        reason=msg,
    )


def skip_off_market_or_ci(reason: str | None = None):
    """Skip test if market is closed AND we're not in CI with FORCE_MARKET_OPEN.

    In CI with FORCE_MARKET_OPEN=1, tests run regardless of market hours.
    """
    msg = reason or "Market is closed (off-hours)"
    return pytest.mark.skipif(
        not is_market_open() and not FORCE_MARKET_OPEN,
        reason=msg,
    )


# ── Common test markers ───────────────────────────────────────────────────

# Use these in conftest.py or test files:

LIVE_API_MARKERS = [
    "live_readonly",
    "sandbox",
    "integration",
]

WEBSOCKET_MARKERS = [
    "live_readonly",
    "sandbox",
]
