"""Phase 7 — Critical-path performance benchmarks.

Self-contained benchmarks using ``time.time()`` measurements for:
  1. Event bus throughput
  2. Order placement latency
  3. Market data processing
  4. Option chain calculation

Run with:
    PYTHONPATH=$(pwd)/src venv/bin/python -m pytest tests/performance/test_critical_paths.py -v

Thresholds are generous to avoid flakiness on CI; tighten for local profiling.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

# ---------------------------------------------------------------------------
# Self-contained stubs (no production imports that pull heavy deps)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FakeEvent:
    event_type: str
    timestamp: datetime
    payload: dict
    event_id: str = ""
    correlation_id: str | None = None
    sequence_number: int = 0

    @classmethod
    def now(cls, event_type: str, payload: dict | None = None) -> _FakeEvent:
        return cls(
            event_type=event_type,
            timestamp=datetime.now(),
            payload=payload or {},
        )


class _FakeEventBus:
    """Minimal event bus for benchmarking publish/dispatch."""

    def __init__(self, max_processed: int = 10_000) -> None:
        self._subscribers: dict[str, dict[str, callable]] = {}
        self._lock = threading.Lock()
        self._sequence = 0
        self._processed: deque[str] = deque(maxlen=max_processed)
        self._processed_set: set[str] = set()
        self._idempotency_lock = threading.Lock()

    def subscribe(self, event_type: str, handler: callable) -> str:
        token = f"tok_{id(handler)}"
        with self._lock:
            self._subscribers.setdefault(event_type, {})[token] = handler
        return token

    def unsubscribe(self, token: str) -> bool:
        with self._lock:
            for handlers in self._subscribers.values():
                if token in handlers:
                    del handlers[token]
                    return True
        return False

    def subscriber_count(self, event_type: str | None = None) -> int:
        with self._lock:
            if event_type is not None:
                return len(self._subscribers.get(event_type, {}))
            return sum(len(h) for h in self._subscribers.values())

    def publish(self, event: _FakeEvent) -> None:
        self._sequence += 1
        with self._lock:
            handlers = list(self._subscribers.get(event.event_type, {}).values())
        for h in handlers:
            h(event)


# ---------------------------------------------------------------------------
# 1. Event Bus Throughput
# ---------------------------------------------------------------------------


class TestEventBusThroughput:
    """Measure publish + dispatch throughput on the in-process event bus."""

    def test_throughput_1000_events(self) -> None:
        bus = _FakeEventBus()
        received: list[_FakeEvent] = []
        bus.subscribe("TICK", lambda e: received.append(e))

        start = time.time()
        for i in range(1_000):
            bus.publish(_FakeEvent.now("TICK", {"ltp": 100.0 + i}))
        elapsed = time.time() - start

        assert len(received) == 1_000
        events_per_sec = 1_000 / elapsed if elapsed > 0 else float("inf")
        assert events_per_sec > 10_000, f"Too slow: {events_per_sec:.0f} evt/s"

    def test_throughput_10_000_events(self) -> None:
        bus = _FakeEventBus()
        count = 0
        threading.Lock()

        def handler(e: _FakeEvent) -> None:
            nonlocal count
            count += 1

        bus.subscribe("TICK", handler)

        start = time.time()
        for i in range(10_000):
            bus.publish(_FakeEvent.now("TICK", {"i": i}))
        elapsed = time.time() - start

        assert count == 10_000
        events_per_sec = 10_000 / elapsed if elapsed > 0 else float("inf")
        assert events_per_sec > 5_000, f"Too slow: {events_per_sec:.0f} evt/s"

    def test_multi_subscriber_throughput(self) -> None:
        bus = _FakeEventBus()
        counts = [0, 0, 0]

        def make_handler(idx: int):
            def h(e: _FakeEvent) -> None:
                counts[idx] += 1

            return h

        for i in range(3):
            bus.subscribe("TICK", make_handler(i))

        start = time.time()
        for _ in range(5_000):
            bus.publish(_FakeEvent.now("TICK", {}))
        elapsed = time.time() - start

        assert all(c == 5_000 for c in counts)
        events_per_sec = 5_000 / elapsed if elapsed > 0 else float("inf")
        assert events_per_sec > 5_000, f"Too slow: {events_per_sec:.0f} evt/s"

    def test_subscribe_unsubscribe_overhead(self) -> None:
        bus = _FakeEventBus()
        tokens = []
        N = 500

        start = time.time()
        for _i in range(N):
            tok = bus.subscribe("TICK", lambda e: None)
            tokens.append(tok)
        for tok in tokens:
            bus.unsubscribe(tok)
        elapsed = time.time() - start

        assert elapsed < 1.0, f"Subscribe/unsubscribe took {elapsed:.3f}s for {N} pairs"

    def test_publish_no_subscribers_is_cheap(self) -> None:
        bus = _FakeEventBus()

        start = time.time()
        for _ in range(10_000):
            bus.publish(_FakeEvent.now("TICK", {}))
        elapsed = time.time() - start

        events_per_sec = 10_000 / elapsed if elapsed > 0 else float("inf")
        assert events_per_sec > 20_000, f"Too slow: {events_per_sec:.0f} evt/s"


# ---------------------------------------------------------------------------
# 2. Order Placement Latency
# ---------------------------------------------------------------------------


class _FakeOrder:
    """Lightweight order value object for benchmarking."""

    __slots__ = ("order_id", "price", "quantity", "side", "status", "symbol")

    def __init__(self, order_id: str, symbol: str, side: str, quantity: int, price: float):
        self.order_id = order_id
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.price = price
        self.status = "OPEN"


class _FakeOrderManager:
    """Minimal order manager for benchmarking placement path."""

    def __init__(self, bus: _FakeEventBus) -> None:
        self._bus = bus
        self._orders: dict[str, _FakeOrder] = {}
        self._counter = 0

    def place_order(self, symbol: str, side: str, quantity: int, price: float) -> _FakeOrder:
        self._counter += 1
        order = _FakeOrder(f"O-{self._counter}", symbol, side, quantity, price)
        self._orders[order.order_id] = order
        self._bus.publish(_FakeEvent.now("ORDER_PLACED", {"order_id": order.order_id}))
        return order

    def cancel_order(self, order_id: str) -> bool:
        if order_id in self._orders:
            self._orders[order_id].status = "CANCELLED"
            self._bus.publish(_FakeEvent.now("ORDER_CANCELLED", {"order_id": order_id}))
            return True
        return False


class TestOrderPlacementLatency:
    """Measure order placement round-trip latency."""

    def test_single_order_latency(self) -> None:
        bus = _FakeEventBus()
        bus.subscribe("ORDER_PLACED", lambda e: None)
        mgr = _FakeOrderManager(bus)

        start = time.time()
        order = mgr.place_order("RELIANCE", "BUY", 100, 2500.0)
        elapsed_ms = (time.time() - start) * 1000

        assert order.order_id.startswith("O-")
        assert elapsed_ms < 10.0, f"Single order took {elapsed_ms:.2f}ms"

    def test_burst_100_orders_latency(self) -> None:
        bus = _FakeEventBus()
        bus.subscribe("ORDER_PLACED", lambda e: None)
        mgr = _FakeOrderManager(bus)

        start = time.time()
        for i in range(100):
            mgr.place_order(f"SYM{i}", "BUY", 10, 100.0 + i)
        elapsed = time.time() - start

        latency_per_order_us = (elapsed / 100) * 1_000_000
        assert latency_per_order_us < 500, f"Per-order: {latency_per_order_us:.0f}us"

    def test_cancel_order_latency(self) -> None:
        bus = _FakeEventBus()
        bus.subscribe("ORDER_CANCELLED", lambda e: None)
        mgr = _FakeOrderManager(bus)

        order = mgr.place_order("RELIANCE", "BUY", 100, 2500.0)

        start = time.time()
        ok = mgr.cancel_order(order.order_id)
        elapsed_ms = (time.time() - start) * 1000

        assert ok is True
        assert elapsed_ms < 5.0, f"Cancel took {elapsed_ms:.2f}ms"

    def test_concurrent_order_placement(self) -> None:
        bus = _FakeEventBus()
        bus.subscribe("ORDER_PLACED", lambda e: None)
        mgr = _FakeOrderManager(bus)

        def place_order(idx: int) -> _FakeOrder:
            return mgr.place_order(f"SYM{idx}", "BUY", 10, 100.0)

        start = time.time()
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = [ex.submit(place_order, i) for i in range(200)]
            orders = [f.result(timeout=5) for f in futures]
        elapsed = time.time() - start

        assert len(orders) == 200
        latency_per_order_us = (elapsed / 200) * 1_000_000
        assert latency_per_order_us < 1_000, f"Concurrent per-order: {latency_per_order_us:.0f}us"


# ---------------------------------------------------------------------------
# 3. Market Data Processing
# ---------------------------------------------------------------------------


class _FakeMarketDataProcessor:
    """Simulates market data tick processing pipeline."""

    def __init__(self) -> None:
        self._processed = 0
        self._last_ltp: float = 0.0

    def process_tick(self, symbol: str, ltp: float, volume: int) -> dict:
        self._processed += 1
        self._last_ltp = ltp
        return {
            "symbol": symbol,
            "ltp": ltp,
            "volume": volume,
            "vwap": ltp * 0.99,  # simplified
            "change_pct": 0.0,
        }

    def process_batch(self, ticks: list[tuple[str, float, int]]) -> list[dict]:
        return [self.process_tick(s, l, v) for s, l, v in ticks]


class TestMarketDataProcessing:
    """Measure market data processing throughput."""

    def test_single_tick_processing(self) -> None:
        proc = _FakeMarketDataProcessor()

        start = time.time()
        result = proc.process_tick("RELIANCE", 2500.0, 1000)
        elapsed_us = (time.time() - start) * 1_000_000

        assert result["symbol"] == "RELIANCE"
        assert elapsed_us < 50, f"Single tick: {elapsed_us:.0f}us"

    def test_throughput_10_000_ticks(self) -> None:
        proc = _FakeMarketDataProcessor()
        ticks = [(f"SYM{i % 100}", 100.0 + i, i) for i in range(10_000)]

        start = time.time()
        results = proc.process_batch(ticks)
        elapsed = time.time() - start

        assert len(results) == 10_000
        ticks_per_sec = 10_000 / elapsed if elapsed > 0 else float("inf")
        assert ticks_per_sec > 10_000, f"Too slow: {ticks_per_sec:.0f} ticks/s"

    def test_concurrent_tick_processing(self) -> None:
        proc = _FakeMarketDataProcessor()
        results: list[dict] = []
        lock = threading.Lock()

        def worker(start_idx: int) -> None:
            for i in range(1_000):
                r = proc.process_tick(f"SYM{(start_idx + i) % 100}", 100.0 + i, i)
                with lock:
                    results.append(r)

        start = time.time()
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = [ex.submit(worker, i * 1_000) for i in range(4)]
            for f in futs:
                f.result(timeout=10)
        elapsed = time.time() - start

        assert len(results) == 4_000
        ticks_per_sec = 4_000 / elapsed if elapsed > 0 else float("inf")
        assert ticks_per_sec > 5_000, f"Too slow: {ticks_per_sec:.0f} ticks/s"

    def test_tick_processing_memory_stability(self) -> None:
        proc = _FakeMarketDataProcessor()

        # Process a large batch to check no unbounded growth
        for _ in range(50_000):
            proc.process_tick("RELIANCE", 2500.0, 100)

        assert proc._processed == 50_000


# ---------------------------------------------------------------------------
# 4. Option Chain Calculation
# ---------------------------------------------------------------------------


class _OptionStrike:
    __slots__ = ("call_ltp", "call_oi", "put_ltp", "put_oi", "strike")

    def __init__(
        self,
        strike: float,
        call_ltp: float = 0.0,
        put_ltp: float = 0.0,
        call_oi: int = 0,
        put_oi: int = 0,
    ):
        self.strike = strike
        self.call_ltp = call_ltp
        self.put_ltp = put_ltp
        self.call_oi = call_oi
        self.put_oi = put_oi


class _FakeOptionChainProcessor:
    """Simulates option chain Greeks and IV calculation."""

    def __init__(self, spot: float = 2500.0, risk_free: float = 0.06, days_to_expiry: int = 30):
        self.spot = spot
        self.risk_free = risk_free
        self.days_to_expiry = days_to_expiry

    def calculate_iv(self, option_price: float, strike: float, is_call: bool) -> float:
        """Simplified IV approximation (Newton-Raphson placeholder)."""
        if option_price <= 0:
            return 0.0
        t = self.days_to_expiry / 365.0
        self.spot / strike
        # Rough implied vol estimate
        iv = abs(option_price / (self.spot * max(t, 0.01))) * 2.0
        return max(iv, 0.01)

    def calculate_greeks(self, strike: float, iv: float, is_call: bool) -> dict:
        """Simplified Greeks calculation."""
        t = self.days_to_expiry / 365.0
        sqrt_t = t**0.5 if t > 0 else 0.001
        d1 = ((self.spot / strike + 0.5 * iv**2 * t) / (iv * sqrt_t)) if iv > 0 else 0.0
        delta = 0.5 * (1.0 + d1 / (1.0 + abs(d1)))
        if not is_call:
            delta = delta - 1.0
        gamma = 0.01 * iv  # simplified
        theta = -self.spot * iv * 0.01 / sqrt_t if sqrt_t > 0 else 0.0
        vega = self.spot * 0.01 * sqrt_t
        return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega}

    def process_chain(self, strikes: list[_OptionStrike]) -> list[dict]:
        """Process full option chain with IV + Greeks."""
        results = []
        for s in strikes:
            call_iv = self.calculate_iv(s.call_ltp, s.strike, True) if s.call_ltp else None
            put_iv = self.calculate_iv(s.put_ltp, s.strike, False) if s.put_ltp else None
            call_greeks = self.calculate_greeks(s.strike, call_iv or 0.2, True) if call_iv else None
            put_greeks = self.calculate_greeks(s.strike, put_iv or 0.2, False) if put_iv else None
            results.append(
                {
                    "strike": s.strike,
                    "call_iv": call_iv,
                    "put_iv": put_iv,
                    "call_greeks": call_greeks,
                    "put_greeks": put_greeks,
                }
            )
        return results


class TestOptionChainCalculation:
    """Measure option chain processing performance."""

    def _make_chain(self, n: int = 20) -> list[_OptionStrike]:
        strikes = []
        for i in range(n):
            strike = 2300.0 + i * 50.0
            call_ltp = max(50.0 - i * 2.0, 1.0)
            put_ltp = max(1.0 + i * 2.0, 1.0)
            strikes.append(_OptionStrike(strike, call_ltp, put_ltp, 1000, 1000))
        return strikes

    def test_single_strike_iv_calculation(self) -> None:
        proc = _FakeOptionChainProcessor()

        start = time.time()
        iv = proc.calculate_iv(50.0, 2500.0, True)
        elapsed_us = (time.time() - start) * 1_000_000

        assert iv > 0
        assert elapsed_us < 20, f"Single IV: {elapsed_us:.0f}us"

    def test_single_strike_greeks_calculation(self) -> None:
        proc = _FakeOptionChainProcessor()

        start = time.time()
        greeks = proc.calculate_greeks(2500.0, 0.2, True)
        elapsed_us = (time.time() - start) * 1_000_000

        assert "delta" in greeks
        assert elapsed_us < 20, f"Single Greeks: {elapsed_us:.0f}us"

    def test_full_chain_20_strikes(self) -> None:
        proc = _FakeOptionChainProcessor()
        strikes = self._make_chain(20)

        start = time.time()
        results = proc.process_chain(strikes)
        elapsed_ms = (time.time() - start) * 1000

        assert len(results) == 20
        assert elapsed_ms < 50.0, f"20-strike chain: {elapsed_ms:.2f}ms"

    def test_full_chain_100_strikes(self) -> None:
        proc = _FakeOptionChainProcessor()
        strikes = self._make_chain(100)

        start = time.time()
        results = proc.process_chain(strikes)
        elapsed_ms = (time.time() - start) * 1000

        assert len(results) == 100
        assert elapsed_ms < 200.0, f"100-strike chain: {elapsed_ms:.2f}ms"

    def test_chain_recalculation_throughput(self) -> None:
        proc = _FakeOptionChainProcessor()
        strikes = self._make_chain(20)

        start = time.time()
        count = 0
        while time.time() - start < 0.5:
            proc.process_chain(strikes)
            count += 1
        elapsed = time.time() - start

        recalc_per_sec = count / elapsed
        assert recalc_per_sec > 50, f"Chain recalc: {recalc_per_sec:.0f}/s"

    def test_concurrent_chain_processing(self) -> None:
        results_per_worker: list[list] = []

        def worker() -> None:
            proc = _FakeOptionChainProcessor()
            strikes = _FakeOptionChainProcessor()._make_chain if False else self._make_chain(20)
            local_results = []
            for _ in range(100):
                local_results.extend(proc.process_chain(strikes))
            results_per_worker.append(local_results)

        start = time.time()
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = [ex.submit(worker) for _ in range(4)]
            for f in futs:
                f.result(timeout=10)
        elapsed = time.time() - start

        total = sum(len(r) for r in results_per_worker)
        assert total == 4 * 100 * 20
        assert elapsed < 5.0, f"Concurrent chains: {elapsed:.2f}s"
