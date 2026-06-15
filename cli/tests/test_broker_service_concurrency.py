"""Concurrency tests for cli.services.broker_service.MockBroker."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

import pytest

from cli.services.broker_service import MockBroker


class TestMockBrokerConcurrency:
    def test_concurrent_place_order_generates_unique_ids(self):
        broker = MockBroker()

        def place():
            return broker.place_order("RELIANCE", "NSE", "BUY", 1)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(place) for _ in range(100)]
            results = [f.result() for f in as_completed(futures)]

        ids = [o.order_id for o in results]
        assert len(ids) == len(set(ids))
        assert all(o.order_id.startswith("DHAN-ORD-") for o in results)

    def test_concurrent_place_order_updates_positions_atomically(self):
        broker = MockBroker()

        def place():
            return broker.place_order("RELIANCE", "NSE", "BUY", 1)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(place) for _ in range(100)]
            for f in as_completed(futures):
                f.result()

        positions = broker.get_positions()
        reliance_positions = [p for p in positions if p.symbol == "RELIANCE"]
        assert len(reliance_positions) == 1
        # Initial mock position has 10 RELIANCE; 100 additional buys -> 110.
        assert reliance_positions[0].quantity == 110

    def test_position_is_immutable_after_fill(self):
        broker = MockBroker()
        broker.place_order("RELIANCE", "NSE", "BUY", 10)
        first = [p for p in broker.get_positions() if p.symbol == "RELIANCE"][0]
        broker.place_order("RELIANCE", "NSE", "BUY", 10)
        second = [p for p in broker.get_positions() if p.symbol == "RELIANCE"][0]

        assert first is not second
        # Initial mock position has 10 RELIANCE; each fill adds 10.
        assert first.quantity == 20
        assert second.quantity == 30
