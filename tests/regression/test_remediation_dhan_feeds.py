"""Regression tests for applied Dhan market-data feed remediations.

These tests pin behaviours that were fixed on the brokers-consolidation
branch. They use DIRECT lazy imports inside each test so that a broken
package ``__init__`` (the mid-refactor ``brokers/dhan/tests`` collection
problem) cannot block collection. If a module truly cannot import we
``pytest.skip`` so collection always stays clean.

Pinned fixes:
  R1  Depth200ConnectionPool.get_feed no longer busy-waits on a rate limiter.
  R2  DhanOrderStream proactive token refresh on auth error (throttled).
  M1  BinaryDepthFeed off_depth/off_quote + staleness threshold + health().
  M4  PollingMarketFeed publishes TICK events and carries OHLC/volume.

Run:
  cd /Users/apple/Downloads/Trade_XV2 && \
    ./venv/bin/python -m pytest tests/regression/test_remediation_dhan_feeds.py -q
"""

from __future__ import annotations

import inspect
import os
import textwrap

import pytest


# =============================================================================
# R1 — Depth200ConnectionPool.get_feed must not busy-wait / sleep-forever
# =============================================================================


def test_r1_get_feed_evicts_oldest_without_busy_wait():
    """get_feed evicts the oldest connection when at max_connections and
    returns promptly (no unbounded ``while not ...: time.sleep(0.1)``).

    NOTE: on this branch ``BinaryDepthFeed`` exposes ``stop()`` but not
    ``close()``; the eviction path in ``Depth200ConnectionPool.get_feed``
    eviction path calls ``feed.close()``; the R1 fix makes BinaryDepthFeed
    define ``close()`` (aliasing stop) so this no longer raises AttributeError.
    The R1 guarantee under test is that get_feed does not busy-wait and returns
    the new feed promptly.
    """
    from brokers.dhan.depth_200 import Depth200ConnectionPool

    pool = Depth200ConnectionPool(
        client_id="CID",
        access_token="TOK",
        max_connections=1,
    )

    feed_a = pool.get_feed(("NSE", "111"))
    # R1 fix: BinaryDepthFeed now defines close(); the eviction path relies on it.
    assert hasattr(feed_a, "close"), "BinaryDepthFeed.close() missing for pool eviction"
    assert pool.has_feed(("NSE", "111"))
    assert len(pool) == 1

    # Second, distinct instrument forces eviction of the oldest (A) and
    # creation of a new feed — must complete without blocking/sleeping.
    feed_b = pool.get_feed(("NSE", "222"))
    assert feed_b is not feed_a
    assert len(pool) == 1
    assert pool.has_feed(("NSE", "222"))
    assert not pool.has_feed(("NSE", "111"))

    pool.close_all()


def test_r1_get_feed_source_has_no_spin_wait():
    """Source-level guard: the removed rate-limiter spin-wait must be gone
    and the evict-oldest replacement must be present.

    Uses AST analysis (not string matching) so the explanatory comment
    that *describes* the removed code does not cause false negatives.
    """
    import ast

    from brokers.dhan.depth_200 import Depth200ConnectionPool

    tree = ast.parse(textwrap.dedent(inspect.getsource(Depth200ConnectionPool.get_feed)))

    # Collect every node inside the function body.
    nodes = list(ast.walk(tree))

    # (1) No time.sleep call anywhere in get_feed → it returns promptly.
    has_sleep = any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "sleep"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "time"
        for n in nodes
    )
    assert not has_sleep, "get_feed must not call time.sleep (no busy-wait)"

    # (2) No reference to the removed rate-limiter predicate.
    has_limiter_ref = any(
        (isinstance(n, ast.Attribute) and n.attr == "can_create_depth_200_connection")
        or (isinstance(n, ast.Name) and n.id == "can_create_depth_200_connection")
        for n in nodes
    )
    assert not has_limiter_ref, "ws_rate_limiter spin-wait predicate must be gone"

    # (3) The evict-oldest replacement strategy is present.
    src = inspect.getsource(Depth200ConnectionPool.get_feed)
    assert "_max_connections" in src
    assert "del self._feeds[oldest_key]" in src


# =============================================================================
# R2 — DhanOrderStream auth-error detection + throttled token refresh
# =============================================================================


def test_r2_order_stream_has_auth_refresh_api():
    """DhanOrderStream exposes the auth-failure helpers and throttle attr."""
    from brokers.dhan.websocket.order_stream import DhanOrderStream

    assert callable(getattr(DhanOrderStream, "_is_auth_error", None))
    assert callable(getattr(DhanOrderStream, "_maybe_refresh_token_on_auth_error", None))
    assert getattr(DhanOrderStream, "_AUTH_REFRESH_THROTTLE_SECONDS", None) == 30.0


def test_r2_auth_error_triggers_refresh_hook():
    """Simulating an auth error invokes the token_refresh_fn and returns True."""
    from brokers.dhan.websocket.order_stream import DhanOrderStream

    calls = []

    def fake_refresh():
        calls.append(1)
        return "NEW_TOKEN"

    stream = DhanOrderStream(
        client_id="CID",
        access_token="OLD",
        token_refresh_fn=fake_refresh,
    )

    exc = RuntimeError("401 Unauthorized: token expired")
    assert stream._is_auth_error(exc) is True
    result = stream._maybe_refresh_token_on_auth_error(exc)

    assert result is True
    assert calls == [1]  # refresh hook fired exactly once
    assert stream._context.get_access_token() == "NEW_TOKEN"


def test_r2_auth_refresh_is_throttled():
    """A second auth error within the 30s throttle window does NOT re-refresh."""
    from brokers.dhan.websocket.order_stream import DhanOrderStream

    calls = []

    def fake_refresh():
        calls.append(1)
        return "NEW_TOKEN"

    stream = DhanOrderStream(
        client_id="CID",
        access_token="OLD",
        token_refresh_fn=fake_refresh,
    )

    exc = RuntimeError("403 Forbidden")
    assert stream._maybe_refresh_token_on_auth_error(exc) is True
    # Immediate second call must be throttled (no new refresh, no tight loop).
    assert stream._maybe_refresh_token_on_auth_error(exc) is False
    assert calls == [1]


def test_r2_create_order_stream_accepts_token_refresh_fn():
    """connection_lifecycle.create_order_stream exposes token_refresh_fn and
    forwards it (plus event_bus) to DhanOrderStream."""
    from brokers.dhan.connection_lifecycle import ConnectionLifecycle

    sig = inspect.signature(ConnectionLifecycle.create_order_stream)
    assert "token_refresh_fn" in sig.parameters

    src = inspect.getsource(ConnectionLifecycle.create_order_stream)
    assert "token_refresh_fn=token_refresh_fn" in src


# =============================================================================
# M1 — BinaryDepthFeed off_depth/off_quote, staleness, health()
# =============================================================================


def _make_binary_depth_feed():
    from brokers.dhan.depth_feed_base import BinaryDepthFeed

    return BinaryDepthFeed(
        client_id="CID",
        access_token="TOK",
        endpoint="wss://example/depth",
        request_code=23,
        total_slots=20,
        subs_per_connection=50,
        depth_type="DEPTH_20",
        name="dhan.depth_20",
        event_name="DEPTH_20",
        header_carries_security_id=True,
    )


def test_m1_off_depth_removes_callback():
    """off_depth removes a callback previously added via on_depth."""
    feed = _make_binary_depth_feed()
    cb = lambda d: None  # noqa: E731
    feed.on_depth(cb)
    assert cb in feed._depth_callbacks
    feed.off_depth(cb)
    assert cb not in feed._depth_callbacks


def test_m1_off_quote_removes_same_callback_list():
    """off_quote removes from the SAME list on_depth appends to."""
    feed = _make_binary_depth_feed()
    cb = lambda d: None  # noqa: E731
    feed.on_depth(cb)
    assert cb in feed._depth_callbacks
    # off_quote must remove it (it targets _depth_callbacks).
    feed.off_quote(cb)
    assert cb not in feed._depth_callbacks
    # And re-adding + off_quote symmetric works.
    feed.on_depth(cb)
    feed.off_quote(cb)
    assert cb not in feed._depth_callbacks


def test_m1_staleness_threshold_default_is_60():
    """_staleness_threshold_seconds honours DHAN_STALENESS_THRESHOLD_SECONDS
    (default 60)."""
    from brokers.dhan.depth_feed_base import BinaryDepthFeed

    prev = os.environ.pop("DHAN_STALENESS_THRESHOLD_SECONDS", None)
    try:
        assert BinaryDepthFeed._staleness_threshold_seconds() == 60.0
        os.environ["DHAN_STALENESS_THRESHOLD_SECONDS"] = "45"
        assert BinaryDepthFeed._staleness_threshold_seconds() == 45.0
    finally:
        if prev is None:
            os.environ.pop("DHAN_STALENESS_THRESHOLD_SECONDS", None)
        else:
            os.environ["DHAN_STALENESS_THRESHOLD_SECONDS"] = prev


def test_m1_health_reports_stale_and_threshold():
    """health() exposes is_stale and staleness_threshold_seconds."""
    feed = _make_binary_depth_feed()
    h = feed.health()
    assert "is_stale" in h.metrics
    assert h.metrics["staleness_threshold_seconds"] == 60.0
    # Not started -> not stale.
    assert h.metrics["is_stale"] is False


# =============================================================================
# M4 — PollingMarketFeed publishes TICK events with populated OHLC/volume
# =============================================================================


class _FakeEventBus:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


def _make_polling_feed(event_bus):
    from brokers.dhan.websocket.polling_feed import PollingMarketFeed

    return PollingMarketFeed(
        http_client=None,
        resolver=None,
        instruments=[("NSE", "123", "ltp")],
        interval_seconds=2.0,
        event_bus=event_bus,
    )


def test_m4_polling_publishes_tick_on_quote():
    """A polled quote results in a TICK DomainEvent on the event bus."""
    from domain.events import DomainEvent

    bus = _FakeEventBus()
    feed = _make_polling_feed(bus)

    segment_data = {
        "123": {
            "last_price": 100.5,
            "open": 90.0,
            "high": 105.0,
            "low": 88.0,
            "close": 95.0,
            "volume": 1000,
            "change": 2.5,
        }
    }
    feed._dispatch_batch_results(segment_data, {123: "123"})

    ticks = [e for e in bus.events if isinstance(e, DomainEvent) and e.event_type == "TICK"]
    assert len(ticks) == 1
    quote = ticks[0].payload["quote"]
    assert quote.ltp == 100.5


def test_m4_polling_carries_ohlc_volume_not_zero():
    """OHLC/volume from the quote are carried through (not zeroed)."""
    from domain.events import DomainEvent

    bus = _FakeEventBus()
    feed = _make_polling_feed(bus)

    segment_data = {
        "123": {
            "last_price": 100.5,
            "open": 90.0,
            "high": 105.0,
            "low": 88.0,
            "close": 95.0,
            "volume": 1000,
            "change": 2.5,
        }
    }
    feed._dispatch_batch_results(segment_data, {123: "123"})

    ticks = [e for e in bus.events if isinstance(e, DomainEvent) and e.event_type == "TICK"]
    q = ticks[0].payload["quote"]
    assert float(q.open) == 90.0
    assert float(q.high) == 105.0
    assert float(q.low) == 88.0
    assert float(q.close) == 95.0
    assert q.volume == 1000
    assert float(q.change) == 2.5


def test_m4_create_polling_feed_forwards_event_bus():
    """connection_lifecycle.create_polling_feed passes event_bus to
    PollingMarketFeed (source-level guard)."""
    from brokers.dhan.connection_lifecycle import ConnectionLifecycle

    src = inspect.getsource(ConnectionLifecycle.create_polling_feed)
    assert "event_bus=self._event_bus" in src
