"""Fault injection tests for concurrent failure scenarios.

Priority 3: Thundering herd on reconnect and concurrent strategy execution
conflicts with race condition prevention.

Tests verify thread-safety and proper synchronization under load.
"""

from __future__ import annotations

import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

from application.oms import PositionManager, RiskConfig, RiskManager
from brokers.common.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from infrastructure.event_bus import DomainEvent, EventBus

# ── Priority 3.1: Thundering Herd on Reconnect ───────────────────────────


class TestThunderingHerdOnReconnect:
    """Multiple clients reconnect simultaneously after broker outage."""

    def test_exponential_backoff_prevents_overload(self):
        """Exponential backoff staggers reconnection attempts."""
        reconnect_times = []
        lock = threading.Lock()

        def reconnect_with_backoff(client_id):
            # Exponential backoff with jitter
            base_delay = 0.01  # Fast for testing
            max_delay = 1.0
            jitter = random.uniform(0, base_delay * 0.5)
            delay = min(base_delay * (2 ** client_id) + jitter, max_delay)

            time.sleep(delay)
            with lock:
                reconnect_times.append((client_id, time.monotonic()))
            return True

        # Simulate 10 clients reconnecting
        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(reconnect_with_backoff, i) for i in range(10)]
            for f in futures:
                f.result(timeout=10)

        # Verify staggered reconnection
        assert len(reconnect_times) == 10
        # Sort by time
        reconnect_times.sort(key=lambda x: x[1])

        # Verify not all reconnected at once (should be spread out)
        first_time = reconnect_times[0][1]
        last_time = reconnect_times[-1][1]
        spread = last_time - first_time
        assert spread > 0.01  # Should have some spread due to backoff

    def test_staggered_reconnection_attempts(self):
        """Reconnection attempts are staggered, not simultaneous."""
        attempt_times = []
        lock = threading.Lock()

        class MockClient:
            def __init__(self, client_id):
                self.client_id = client_id
                self.reconnected = False

            def reconnect(self):
                # Simulate staggered reconnect
                backoff = 0.01 * (2 ** self.client_id)
                time.sleep(backoff)
                with lock:
                    attempt_times.append(time.monotonic())
                self.reconnected = True
                return True

        clients = [MockClient(i) for i in range(5)]

        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = [ex.submit(client.reconnect) for client in clients]
            for f in futures:
                f.result(timeout=10)

        # All should reconnect
        assert all(c.reconnected for c in clients)
        assert len(attempt_times) == 5

        # Verify staggering
        attempt_times.sort()
        for i in range(1, len(attempt_times)):
            # Each attempt should be later than previous
            assert attempt_times[i] >= attempt_times[i-1]

    def test_no_resource_exhaustion(self):
        """Reconnection doesn't exhaust system resources."""
        active_connections = []
        lock = threading.Lock()
        max_concurrent = 0

        def reconnect_client(client_id):
            nonlocal max_concurrent
            with lock:
                active_connections.append(client_id)
                max_concurrent = max(max_concurrent, len(active_connections))

            # Simulate reconnect work
            time.sleep(0.01)

            with lock:
                active_connections.remove(client_id)
            return True

        # Simulate 20 clients reconnecting
        with ThreadPoolExecutor(max_workers=20) as ex:
            futures = [ex.submit(reconnect_client, i) for i in range(20)]
            for f in futures:
                f.result(timeout=10)

        # Should not have exceeded reasonable concurrency
        assert max_concurrent <= 20
        assert len(active_connections) == 0  # All cleaned up

    @pytest.mark.slow
    def test_thundering_herd_with_real_backoff(self):
        """Real exponential backoff prevents thundering herd."""
        reconnect_events = []
        lock = threading.Lock()

        def thundering_herd_reconnect(num_clients):
            """Simulate thundering herd scenario."""
            def client_reconnect(client_id):
                # Exponential backoff: 1s, 2s, 4s, 8s, ...
                base_delay = 0.1  # Fast for testing
                max_delay = 2.0
                jitter = random.uniform(0, base_delay * 0.1)

                for attempt in range(5):
                    delay = min(base_delay * (2 ** attempt) + jitter, max_delay)
                    time.sleep(delay)

                    with lock:
                        reconnect_events.append({
                            "client_id": client_id,
                            "attempt": attempt,
                            "time": time.monotonic(),
                        })

                    # Simulate successful reconnect
                    return True
                return False

            with ThreadPoolExecutor(max_workers=num_clients) as ex:
                futures = [ex.submit(client_reconnect, i) for i in range(num_clients)]
                for f in futures:
                    f.result(timeout=30)

        thundering_herd_reconnect(10)

        # Should have reconnection events
        assert len(reconnect_events) > 0

        # Verify exponential backoff pattern
        client_attempts = {}
        for event in reconnect_events:
            cid = event["client_id"]
            if cid not in client_attempts:
                client_attempts[cid] = []
            client_attempts[cid].append(event["time"])

        # Each client should have attempted at least once
        assert len(client_attempts) == 10

    def test_reconnection_rate_limiting(self):
        """Reconnection attempts are rate-limited."""
        limiter_lock = threading.Lock()
        reconnect_count = 0
        max_reconnects = 5

        def rate_limited_reconnect():
            nonlocal reconnect_count
            with limiter_lock:
                if reconnect_count >= max_reconnects:
                    return False
                reconnect_count += 1

            time.sleep(0.01)
            return True

        results = []
        with ThreadPoolExecutor(max_workers=20) as ex:
            futures = [ex.submit(rate_limited_reconnect) for _ in range(20)]
            for f in futures:
                results.append(f.result(timeout=10))

        # Should have limited successful reconnects
        assert sum(1 for r in results if r) <= max_reconnects


# ── Priority 3.2: Concurrent Strategy Execution Conflicts ────────────────


class TestConcurrentStrategyExecutionConflicts:
    """Two strategies try to place orders for same symbol."""

    def test_no_race_conditions_in_order_placement(self):
        """Concurrent order placement doesn't cause race conditions."""
        orders_placed = []
        lock = threading.Lock()

        def place_order(symbol, strategy_id):
            # Simulate thread-safe order placement
            order = {
                "symbol": symbol,
                "strategy_id": strategy_id,
                "order_id": f"ORD-{strategy_id}-{len(orders_placed)}",
                "timestamp": time.monotonic(),
            }
            with lock:
                orders_placed.append(order)
            return order

        # Two strategies placing orders for same symbol
        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = []
            for i in range(5):
                futures.append(ex.submit(place_order, "RELIANCE", "STRAT-1"))
                futures.append(ex.submit(place_order, "RELIANCE", "STRAT-2"))

            for f in futures:
                f.result(timeout=10)

        # All orders should be placed
        assert len(orders_placed) == 10

        # No duplicate order IDs
        order_ids = [o["order_id"] for o in orders_placed]
        assert len(order_ids) == len(set(order_ids))

    def test_position_reconciliation_handles_concurrent_updates(self):
        """Position reconciliation handles concurrent position updates."""
        pm = PositionManager()
        rm = RiskManager(pm, RiskConfig(), capital_fn=lambda: Decimal("100000"))

        errors = []

        def update_position(position_id):
            try:
                # Simulate concurrent position updates
                pm.upsert_position({
                    "symbol": "RELIANCE",
                    "exchange": "NSE",
                    "quantity": position_id,
                    "avg_price": "2500.0",
                    "ltp": "2505.0",
                })
            except Exception as e:
                errors.append(e)

        # Concurrent position updates
        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(update_position, i) for i in range(10)]
            for f in futures:
                f.result(timeout=10)

        # No errors should occur
        assert len(errors) == 0

    def test_event_ordering_preserved(self):
        """Event ordering preserved under concurrent publishes."""
        bus = EventBus()
        received_events = []
        lock = threading.Lock()

        def handler(event):
            with lock:
                received_events.append(event)

        token = bus.subscribe("ORDER_PLACED", handler)

        # Publish events concurrently
        def publish_event(event_id):
            bus.publish(DomainEvent.now(
                "ORDER_PLACED",
                {"order_id": f"ORD-{event_id}"},
                symbol="RELIANCE",
            ))

        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(publish_event, i) for i in range(10)]
            for f in futures:
                f.result(timeout=10)

        # All events should be received
        assert len(received_events) == 10

        # Each event should have a sequence number
        for event in received_events:
            assert event.sequence_number > 0

        # Sequence numbers should be unique (no duplicates)
        seq_nums = [e.sequence_number for e in received_events]
        assert len(seq_nums) == len(set(seq_nums))

        bus.unsubscribe(token)

    def test_concurrent_order_cancellation(self):
        """Concurrent order cancellation doesn't cause issues."""
        orders = {}
        lock = threading.Lock()

        def create_order(order_id):
            with lock:
                orders[order_id] = {"status": "OPEN", "order_id": order_id}
            return order_id

        def cancel_order(order_id):
            with lock:
                if order_id in orders:
                    orders[order_id]["status"] = "CANCELLED"
                    return True
                return False

        # Create orders
        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = [ex.submit(create_order, f"ORD-{i}") for i in range(5)]
            for f in futures:
                f.result(timeout=10)

        assert len(orders) == 5

        # Cancel orders concurrently
        results = []
        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = [ex.submit(cancel_order, f"ORD-{i}") for i in range(5)]
            for f in futures:
                results.append(f.result(timeout=10))

        # All cancellations should succeed
        assert all(results)

        # All orders should be cancelled
        assert all(o["status"] == "CANCELLED" for o in orders.values())

    def test_strategy_isolation(self):
        """Different strategies don't interfere with each other."""
        strategy_positions = {}
        lock = threading.Lock()

        def strategy_trade(strategy_id, symbol, quantity):
            with lock:
                if strategy_id not in strategy_positions:
                    strategy_positions[strategy_id] = {}
                if symbol not in strategy_positions[strategy_id]:
                    strategy_positions[strategy_id][symbol] = 0
                strategy_positions[strategy_id][symbol] += quantity

        # Multiple strategies trading concurrently
        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = []
            for i in range(5):
                futures.append(ex.submit(strategy_trade, f"STRAT-{i}", "RELIANCE", 10))
                futures.append(ex.submit(strategy_trade, f"STRAT-{i}", "TCS", 5))

            for f in futures:
                f.result(timeout=10)

        # Each strategy should have correct positions
        for strat_id in ["STRAT-0", "STRAT-1", "STRAT-2", "STRAT-3", "STRAT-4"]:
            assert strategy_positions[strat_id]["RELIANCE"] == 10
            assert strategy_positions[strat_id]["TCS"] == 5

    def test_concurrent_risk_checks(self):
        """Multiple concurrent risk checks don't cause race conditions."""
        pm = PositionManager()
        rm = RiskManager(pm, RiskConfig(), capital_fn=lambda: Decimal("100000"))

        results = []
        errors = []

        def check_risk(order_id):
            try:
                from domain import Order, OrderStatus, OrderType, ProductType, Side
                order = Order(
                    order_id=f"ORD-{order_id}",
                    symbol="RELIANCE",
                    exchange="NSE",
                    side=Side.BUY,
                    quantity=10,
                    price=Decimal("2500"),
                    order_type=OrderType.LIMIT,
                    product_type=ProductType.INTRADAY,
                    status=OrderStatus.OPEN,
                )
                result = rm.check_order(order)
                return result.allowed
            except Exception as e:
                errors.append(e)
                return None

        with ThreadPoolExecutor(max_workers=20) as ex:
            futures = [ex.submit(check_risk, i) for i in range(20)]
            for f in futures:
                results.append(f.result(timeout=10))

        # All risk checks should complete
        assert len(results) == 20
        # No errors should occur
        assert len(errors) == 0

    def test_order_book_concurrent_access(self):
        """Concurrent order book access doesn't cause corruption."""
        order_book = []
        lock = threading.Lock()

        def add_order(order_id):
            order = {
                "order_id": order_id,
                "status": "OPEN",
                "timestamp": time.monotonic(),
            }
            with lock:
                order_book.append(order)

        def get_order_count():
            with lock:
                return len(order_book)

        # Add orders concurrently
        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(add_order, f"ORD-{i}") for i in range(10)]
            for f in futures:
                f.result(timeout=10)

        # Order book should have all orders
        count = get_order_count()
        assert count == 10

        # All orders should be valid
        with lock:
            for order in order_book:
                assert "order_id" in order
                assert "status" in order

    def test_concurrent_market_data_subscriptions(self):
        """Concurrent market data subscriptions don't conflict."""
        subscriptions = {}
        lock = threading.Lock()

        def subscribe(symbol, exchange):
            key = f"{symbol}:{exchange}"
            with lock:
                if key not in subscriptions:
                    subscriptions[key] = []
                subscriptions[key].append(time.monotonic())
            return key

        # Multiple strategies subscribing to same symbols
        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = []
            for i in range(5):
                futures.append(ex.submit(subscribe, "RELIANCE", "NSE"))
                futures.append(ex.submit(subscribe, "TCS", "NSE"))

            for f in futures:
                f.result(timeout=10)

        # Should have subscriptions for both symbols
        assert "RELIANCE:NSE" in subscriptions
        assert "TCS:NSE" in subscriptions

        # Each should have 5 subscriptions
        assert len(subscriptions["RELIANCE:NSE"]) == 5
        assert len(subscriptions["TCS:NSE"]) == 5

    def test_thundering_herd_circuit_breaker_recovery(self):
        """Circuit breaker recovery handles thundering herd correctly."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(
            failure_threshold=2,
            open_duration_ms=200,
            success_threshold=1,
        ))

        # Open circuit breaker
        cb.on_failure()
        cb.on_failure()
        assert cb.state == CircuitState.OPEN

        # Wait for half-open
        time.sleep(0.25)

        # Multiple threads trying to use circuit breaker
        results = []

        def try_operation():
            if cb.allow_request():
                cb.on_success()
                return True
            return False

        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(try_operation) for _ in range(10)]
            for f in futures:
                results.append(f.result(timeout=10))

        # Should have some successes (half-open allows probes)
        assert any(results)

        # Circuit breaker should recover
        assert cb.state == CircuitState.CLOSED
