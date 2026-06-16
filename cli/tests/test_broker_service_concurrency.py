"""Concurrency tests for the shared MockBroker (brokers.paper.mock_broker)."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

import pytest

from brokers.paper.mock_broker import MockBroker


class TestMockBrokerConcurrency:
    def test_concurrent_place_order_generates_unique_ids(self):
        broker = MockBroker()

        def place():
            return broker.place_order("RELIANCE", "NSE", "BUY", 1)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(place) for _ in range(100)]
            results = [f.result() for f in as_completed(futures)]

        ids = [o.order_id for o in results]
        assert len(ids) == len(set(ids)), "All order IDs must be unique"
        assert all(o.order_id for o in results), "All order IDs must be non-empty"

    def test_concurrent_place_order_updates_positions(self):
        broker = MockBroker()

        def place():
            return broker.place_order("RELIANCE", "NSE", "BUY", 1)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(place) for _ in range(20)]
            for f in as_completed(futures):
                f.result()

        positions = broker.positions()
        reliance_positions = [p for p in positions if p.symbol == "RELIANCE"]
        assert len(reliance_positions) >= 1
        total_qty = sum(p.quantity for p in reliance_positions)
        assert total_qty == 20, f"Expected 20 total quantity, got {total_qty}"

    def test_positions_reflect_fills(self):
        broker = MockBroker()
        broker.place_order("RELIANCE", "NSE", "BUY", 10)
        positions_after_first = broker.positions()
        reliance_1 = [p for p in positions_after_first if p.symbol == "RELIANCE"]
        assert len(reliance_1) >= 1

        broker.place_order("RELIANCE", "NSE", "BUY", 10)
        positions_after_second = broker.positions()
        reliance_2 = [p for p in positions_after_second if p.symbol == "RELIANCE"]
        assert len(reliance_2) >= 1

        qty_1 = sum(p.quantity for p in reliance_1)
        qty_2 = sum(p.quantity for p in reliance_2)
        assert qty_2 > qty_1, "Second fill should increase position quantity"
