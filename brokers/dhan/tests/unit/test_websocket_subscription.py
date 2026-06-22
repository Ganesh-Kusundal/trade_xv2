"""Tests for DhanSubscriptionManager — subscription state management."""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

import pytest

from brokers.dhan.ws_subscription import DhanSubscriptionManager


class TestSubscriptionInit:
    """Verify subscription manager initialization."""

    def test_init_empty(self):
        """Must start with no subscriptions."""
        mgr = DhanSubscriptionManager(max_instruments=1000)
        assert mgr.active_count == 0
        assert list(mgr.active_instruments) == []

    def test_init_with_instruments(self):
        """Must accept initial instrument list."""
        instruments = [(1, 2885, 15), (1, 2886, 17)]
        mgr = DhanSubscriptionManager(max_instruments=1000, initial=instruments)
        assert mgr.active_count == 2
        assert (1, 2885, 15) in mgr.active_instruments

    def test_init_deduplicates(self):
        """Must deduplicate initial instruments."""
        instruments = [(1, 2885, 15), (1, 2885, 15), (1, 2886, 17)]
        mgr = DhanSubscriptionManager(max_instruments=1000, initial=instruments)
        assert mgr.active_count == 2


class TestSubscribe:
    """Verify subscribe behavior."""

    def test_subscribe_new_instrument(self):
        """Must add new instrument to active set."""
        mgr = DhanSubscriptionManager(max_instruments=1000)
        new_instruments = mgr.subscribe([(1, 2885, 15)])
        assert len(new_instruments) == 1
        assert (1, 2885, 15) in mgr.active_instruments
        assert mgr.active_count == 1

    def test_subscribe_deduplicates(self):
        """Must not add already-subscribed instruments."""
        mgr = DhanSubscriptionManager(max_instruments=1000)
        mgr.subscribe([(1, 2885, 15)])
        new_instruments = mgr.subscribe([(1, 2885, 15)])
        assert len(new_instruments) == 0
        assert mgr.active_count == 1

    def test_subscribe_mixed_new_and_existing(self):
        """Must return only new instruments when mix is provided."""
        mgr = DhanSubscriptionManager(max_instruments=1000)
        mgr.subscribe([(1, 2885, 15)])
        new_instruments = mgr.subscribe([(1, 2885, 15), (1, 2886, 17)])
        assert len(new_instruments) == 1
        assert (1, 2886, 17) in new_instruments
        assert mgr.active_count == 2

    def test_subscribe_exceeds_limit(self):
        """Must raise ValueError when limit would be exceeded."""
        mgr = DhanSubscriptionManager(max_instruments=2)
        mgr.subscribe([(1, 2885, 15), (1, 2886, 17)])
        with pytest.raises(ValueError, match="limit"):
            mgr.subscribe([(1, 2887, 15)])

    def test_subscribe_at_limit_boundary(self):
        """Must succeed when exactly at limit."""
        mgr = DhanSubscriptionManager(max_instruments=2)
        mgr.subscribe([(1, 2885, 15)])
        mgr.subscribe([(1, 2886, 17)])
        assert mgr.active_count == 2

    def test_subscribe_empty_list(self):
        """Must handle empty subscribe list gracefully."""
        mgr = DhanSubscriptionManager(max_instruments=1000)
        new_instruments = mgr.subscribe([])
        assert len(new_instruments) == 0
        assert mgr.active_count == 0

    def test_subscribe_near_limit_succeeds(self):
        """Must succeed when near but not exceeding limit."""
        mgr = DhanSubscriptionManager(max_instruments=10)
        # Subscribe 8 instruments (80% of 10)
        instruments = [(1, i, 15) for i in range(1, 9)]
        # Should not raise
        new_insts = mgr.subscribe(instruments)
        assert len(new_insts) == 8
        assert mgr.active_count == 8


class TestUnsubscribe:
    """Verify unsubscribe behavior."""

    def test_unsubscribe_existing(self):
        """Must remove instrument from active set."""
        mgr = DhanSubscriptionManager(max_instruments=1000)
        mgr.subscribe([(1, 2885, 15)])
        mgr.unsubscribe([(1, 2885, 15)])
        assert (1, 2885, 15) not in mgr.active_instruments
        assert mgr.active_count == 0

    def test_unsubscribe_nonexistent(self):
        """Must handle unsubscribe of non-existent instrument gracefully."""
        mgr = DhanSubscriptionManager(max_instruments=1000)
        mgr.unsubscribe([(1, 9999, 15)])
        assert mgr.active_count == 0

    def test_unsubscribe_partial_match(self):
        """Must only remove specified instruments."""
        mgr = DhanSubscriptionManager(max_instruments=1000)
        mgr.subscribe([(1, 2885, 15), (1, 2886, 17)])
        mgr.unsubscribe([(1, 2885, 15)])
        assert (1, 2885, 15) not in mgr.active_instruments
        assert (1, 2886, 17) in mgr.active_instruments
        assert mgr.active_count == 1

    def test_unsubscribe_empty_list(self):
        """Must handle empty unsubscribe list gracefully."""
        mgr = DhanSubscriptionManager(max_instruments=1000)
        mgr.subscribe([(1, 2885, 15)])
        mgr.unsubscribe([])
        assert mgr.active_count == 1


class TestValidation:
    """Verify exchange code validation."""

    def test_validate_known_exchange(self):
        """Must accept known exchange codes."""
        mgr = DhanSubscriptionManager(max_instruments=1000)
        mgr.validate_exchange("NSE_EQ")
        mgr.validate_exchange("MCX_COMM")
        mgr.validate_exchange("BSE_EQ")

    def test_validate_unknown_exchange(self):
        """Must raise ValueError for unknown exchange codes."""
        mgr = DhanSubscriptionManager(max_instruments=1000)
        with pytest.raises(ValueError, match="Unknown exchange"):
            mgr.validate_exchange("INVALID_EXCHANGE")

    def test_validate_instruments(self):
        """Must validate all instruments in a list."""
        mgr = DhanSubscriptionManager(max_instruments=1000)
        mgr.validate_instruments([("NSE_EQ", "2885", "LTP")])

    def test_validate_instruments_with_unknown(self):
        """Must raise when any instrument has unknown exchange."""
        mgr = DhanSubscriptionManager(max_instruments=1000)
        with pytest.raises(ValueError, match="Unknown exchange"):
            mgr.validate_instruments([("INVALID", "2885", "LTP")])


class TestSubscriptionThreadSafety:
    """Verify thread safety of subscription manager."""

    def test_concurrent_subscribe_unsubscribe(self):
        """Concurrent subscribe/unsubscribe must not corrupt state."""
        import threading

        mgr = DhanSubscriptionManager(max_instruments=10000)
        errors = []

        def subscribe_thread(start_id, count):
            try:
                for i in range(start_id, start_id + count):
                    mgr.subscribe([(1, i, 15)])
            except Exception as e:
                errors.append(e)

        def unsubscribe_thread(start_id, count):
            try:
                for i in range(start_id, start_id + count):
                    mgr.unsubscribe([(1, i, 15)])
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(5):
            t1 = threading.Thread(target=subscribe_thread, args=(i * 100, 100))
            t2 = threading.Thread(target=unsubscribe_thread, args=(i * 100, 50))
            threads.extend([t1, t2])

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert len(errors) == 0
        assert mgr.active_count >= 0
