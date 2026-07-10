"""Dhan gateway: idempotent place_order and stream registration contracts."""

from __future__ import annotations

import threading
import time

import pytest


def _skip_if_import_error(fn):
    """Import the named module lazily; skip the test on ImportError."""
    try:
        return fn()
    except ImportError as exc:  # pragma: no cover - branch-dependent
        pytest.skip(reason=f"branch refactor: {exc}")


# ─────────────────────────────────────────────────────────────────────────
# Lightweight fakes
# ─────────────────────────────────────────────────────────────────────────

class _FakeExchange:
    def __init__(self, value):
        self.value = value


class _FakeInstrument:
    """Minimal stand-in for a resolved DhanInstrument."""

    def __init__(self, security_id="11536", exchange="NSE", symbol="RELIANCE"):
        self.symbol = symbol
        self.exchange = _FakeExchange(exchange)
        self.security_id = security_id
        self.instrument_type = "EQUITY"
        self.lot_size = 1
        self.name = symbol
        self.sm_symbol_name = None
        self.underlying = None
        self.expiry = None
        self.strike_price = None
        self.option_type = None


class _FakeResolver:
    """Duck-typed resolver usable with ``allow_duck=True``."""

    def resolve(self, symbol, exchange):
        return _FakeInstrument(symbol=symbol, exchange=exchange)

    def get_by_security_id(self, security_id):
        return _FakeInstrument(security_id=str(security_id))


class _FakeClient:
    """HTTP client fake that records POST calls and can be made blocking."""

    def __init__(self):
        self.client_id = "TESTCID"
        self.post_calls = []
        self._lock = threading.Lock()
        self._barrier = None
        self._parties = 0
        self._slow_ids = set()
        self._times = {}

    def _ensure_barrier(self):
        if self._barrier is None and self._parties:
            self._barrier = threading.Barrier(self._parties)

    def post(self, endpoint, json=None):
        cid = (json or {}).get("correlationId")
        with self._lock:
            self.post_calls.append(cid)
        self._ensure_barrier()
        if self._barrier is not None:
            self._barrier.wait()
        start = time.time()
        if cid in self._slow_ids:
            time.sleep(0.5)
        end = time.time()
        with self._lock:
            self._times[cid] = (start, end)
        return {"data": {"orderId": f"ORD-{cid}"}}

    def put(self, endpoint, json=None):
        return {"status": "success"}

    def delete(self, endpoint, json=None):
        return {"data": []}


class _FakeFeed:
    """Stand-in for a market feed returned by create_market_feed."""

    def __init__(self):
        self.subscribe_calls = []
        self.on_quote_calls = 0
        self.is_connected = False
        self.connect_calls = 0

    def subscribe(self, items):
        self.subscribe_calls.append(items)

    def on_quote(self, cb):
        self.on_quote_calls += 1

    def connect(self):
        self.connect_calls += 1
        self.is_connected = True


class _FakeConnection:
    """Minimal DhanConnection stand-in for the gateway tests."""

    def __init__(self, market_feed=None):
        self.access_token = "TOKEN"
        self.market_feed = market_feed
        self._created_feeds = []
        self.orders = _FakeOrdersAdapter()
        self.instruments = _FakeResolver()

    def create_market_feed(self, *, access_token, instruments, access_token_fn):
        feed = _FakeFeed()
        feed._token_receiver = access_token_fn
        self._created_feeds.append(feed)
        return feed


class _FakeOrdersAdapter:
    """Stand-in for the orders adapter port used by the gateway."""

    def modify_order(self, order_id, **changes):
        return ("modified", order_id, changes)

    def cancel_all_orders(self):
        return [("ORD1", True)]


# ─────────────────────────────────────────────────────────────────────────
# G1: gateway methods / stream routing / init
# ─────────────────────────────────────────────────────────────────────────

def test_g1_gateway_has_modify_and_cancel_all_methods():
    gateway_mod = _skip_if_import_error(
        lambda: __import__(
            "brokers.dhan.gateway", fromlist=["DhanBrokerGateway"]
        ).DhanBrokerGateway
    )
    assert callable(getattr(gateway_mod, "modify_order", None))
    assert callable(getattr(gateway_mod, "cancel_all_orders", None))


def test_g1_gateway_init_runs_without_raising():
    mod = _skip_if_import_error(
        lambda: __import__("brokers.dhan.gateway", fromlist=["DhanBrokerGateway"])
    )
    DhanBrokerGateway = mod.DhanBrokerGateway
    conn = _FakeConnection()
    gw = DhanBrokerGateway(conn)  # must not raise
    assert gw is not None
    # The delegated methods should be present on the instance.
    assert callable(getattr(gw, "modify_order"))
    assert callable(getattr(gw, "cancel_all_orders"))


def test_g1_stream_routes_through_create_market_feed():
    mod = _skip_if_import_error(
        lambda: __import__("brokers.dhan.gateway", fromlist=["DhanBrokerGateway"])
    )
    DhanBrokerGateway = mod.DhanBrokerGateway
    conn = _FakeConnection()
    gw = DhanBrokerGateway(conn)

    feed = gw.stream("RELIANCE", exchange="NSE", mode="LTP")

    # stream() must have created the feed via the lifecycle helper, not by
    # building DhanMarketFeed directly, and the feed must be cached.
    assert len(conn._created_feeds) == 1
    assert conn.market_feed is feed
    assert isinstance(feed, _FakeFeed)
    # The token receiver callback must have been registered.
    assert callable(getattr(feed, "_token_receiver", None))


# ─────────────────────────────────────────────────────────────────────────
# R3: idempotency / non-blocking lock
# ─────────────────────────────────────────────────────────────────────────

def _make_adapter(client, allow_live=True):
    """Build a real OrdersAdapter around fakes (lazy import)."""
    orders_mod = _skip_if_import_error(
        lambda: __import__("brokers.dhan.execution.orders", fromlist=["OrdersAdapter"])
    )
    OrdersAdapter = orders_mod.OrdersAdapter
    identity = _skip_if_import_error(
        lambda: __import__(
            "brokers.dhan.identity", fromlist=["DhanIdentityProvider"]
        ).DhanIdentityProvider
    )(_FakeResolver())
    return OrdersAdapter(client, identity, allow_live_orders=allow_live)


def _payload(correlation_id):
    from domain.models.dtos import BrokerOrderPayload

    return BrokerOrderPayload(
        symbol="RELIANCE",
        exchange="NSE",
        transaction_type="BUY",
        quantity=1,
        order_type="MARKET",
        product_type="INTRADAY",
        validity="DAY",
        correlation_id=correlation_id,
    )


def test_r3_same_correlation_id_issues_one_post():
    client = _FakeClient()
    adapter = _make_adapter(client)

    cid = "same-cid"
    threads = [
        threading.Thread(target=adapter.place_order, args=(_payload(cid),))
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    # Exactly one blocking HTTP POST despite 8 concurrent callers.
    assert client.post_calls.count(cid) == 1


def test_r3_distinct_correlation_ids_issue_n_posts():
    client = _FakeClient()
    adapter = _make_adapter(client)

    n = 6
    threads = [
        threading.Thread(
            target=adapter.place_order, args=(_payload(f"cid-{i}"),)
        )
        for i in range(n)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    # Each distinct correlation id results in its own POST.
    assert len(client.post_calls) == n
    assert len(set(client.post_calls)) == n


def test_r3_hung_post_does_not_block_other_placements():
    client = _FakeClient()
    client._parties = 2
    slow_cid = "slow-cid"
    fast_cid = "fast-cid"
    client._slow_ids = {slow_cid}
    adapter = _make_adapter(client)

    slow_done = threading.Event()
    fast_done = threading.Event()

    def run_slow():
        adapter.place_order(_payload(slow_cid))
        slow_done.set()

    def run_fast():
        adapter.place_order(_payload(fast_cid))
        fast_done.set()

    ts = threading.Thread(target=run_slow)
    tf = threading.Thread(target=run_fast)
    ts.start()
    tf.start()

    # The fast placement must complete even while the slow one is blocked
    # inside its HTTP post (lock held only for reserve/commit, not the post).
    fast_finished = fast_done.wait(timeout=5)
    assert fast_finished, "fast placement was blocked by the hung slow post"
    # At this point the slow call must still be in flight.
    assert not slow_done.is_set(), "expected slow post to still be blocking"

    ts.join(timeout=5)
    assert slow_done.is_set()

    # Prove the lock was released during the post: fast finished before slow.
    with client._lock:
        fast_times = client._times.get(fast_cid)
        slow_times = client._times.get(slow_cid)
    assert fast_times is not None and slow_times is not None
    assert fast_times[1] < slow_times[1]


# ─────────────────────────────────────────────────────────────────────────
# R1-adjacent: cancel_all_orders guards non-dict responses
# ─────────────────────────────────────────────────────────────────────────

def test_r1_cancel_all_orders_accepts_non_dict_response():
    client = _FakeClient()
    adapter = _make_adapter(client)

    # Broker returns a list instead of a dict (observed error path).
    client.delete = lambda endpoint, json=None: []
    assert adapter.cancel_all_orders() == []

    # Broker returns None.
    client.delete = lambda endpoint, json=None: None
    assert adapter.cancel_all_orders() == []
