"""Tests for ProcessedTradeRepository singleton enforcement (P0.6).

These tests verify that:
1. Only ONE instance exists per persistence path
2. Different persistence paths create different instances
3. The singleton pattern is thread-safe
4. Backward compatibility with direct instantiation is maintained
"""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from infrastructure.event_bus.processed_trade_repository import (
    ProcessedTradeRepository,
    TradeIdKey,
)


class TestProcessedTradeRepositorySingleton:
    """Test singleton pattern enforcement."""

    def setup_method(self) -> None:
        """Clear singleton registry before each test."""
        ProcessedTradeRepository._instances.clear()

    def teardown_method(self) -> None:
        """Clean up singleton registry after each test."""
        ProcessedTradeRepository._instances.clear()

    def test_get_instance_returns_same_object(self) -> None:
        """Multiple calls to get_instance() should return the same object."""
        instance1 = ProcessedTradeRepository.get_instance()
        instance2 = ProcessedTradeRepository.get_instance()

        assert instance1 is instance2

    def test_get_instance_without_args_uses_default_key(self) -> None:
        """get_instance() without args should use 'default' key."""
        instance = ProcessedTradeRepository.get_instance()
        assert "default" in ProcessedTradeRepository._instances
        assert ProcessedTradeRepository._instances["default"] is instance

    def test_different_persistence_paths_create_different_instances(self) -> None:
        """Different persistence paths should create different instances."""
        instance1 = ProcessedTradeRepository.get_instance(persistence_path="/tmp/path1.jsonl")
        instance2 = ProcessedTradeRepository.get_instance(persistence_path="/tmp/path2.jsonl")

        assert instance1 is not instance2
        assert "/tmp/path1.jsonl" in ProcessedTradeRepository._instances
        assert "/tmp/path2.jsonl" in ProcessedTradeRepository._instances

    def test_same_persistence_path_returns_same_instance(self) -> None:
        """Same persistence path should return the same instance."""
        instance1 = ProcessedTradeRepository.get_instance(persistence_path="/tmp/same_path.jsonl")
        instance2 = ProcessedTradeRepository.get_instance(persistence_path="/tmp/same_path.jsonl")

        assert instance1 is instance2

    def test_none_persistence_path_uses_default_key(self) -> None:
        """None persistence_path should use 'default' key."""
        instance1 = ProcessedTradeRepository.get_instance(persistence_path=None)
        instance2 = ProcessedTradeRepository.get_instance()

        assert instance1 is instance2

    def test_instance_is_actually_created(self) -> None:
        """get_instance should create a real ProcessedTradeRepository."""
        instance = ProcessedTradeRepository.get_instance()

        assert isinstance(instance, ProcessedTradeRepository)
        assert hasattr(instance, "is_processed")
        assert hasattr(instance, "mark_processed")

    def test_direct_constructor_still_works(self) -> None:
        """Direct instantiation should still work for backward compatibility."""
        # Direct construction should NOT register in singleton registry
        instance = ProcessedTradeRepository()
        assert "default" not in ProcessedTradeRepository._instances

        # But get_instance should still work
        singleton = ProcessedTradeRepository.get_instance()
        assert singleton is not instance


class TestProcessedTradeRepositorySingletonThreadSafety:
    """Test that singleton pattern is thread-safe."""

    def setup_method(self) -> None:
        ProcessedTradeRepository._instances.clear()

    def teardown_method(self) -> None:
        ProcessedTradeRepository._instances.clear()

    def test_concurrent_get_instance_returns_same_object(self) -> None:
        """Multiple threads calling get_instance() should get the same object."""
        instances = []
        lock = threading.Lock()

        def get_instance() -> None:
            instance = ProcessedTradeRepository.get_instance()
            with lock:
                instances.append(instance)

        threads = [threading.Thread(target=get_instance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should have the same instance
        assert len(instances) == 10
        assert all(inst is instances[0] for inst in instances)

    def test_concurrent_get_instance_different_paths(self) -> None:
        """Threads requesting different paths should get different instances."""
        instances = []
        lock = threading.Lock()

        def get_instance_with_path(path: str) -> None:
            instance = ProcessedTradeRepository.get_instance(persistence_path=path)
            with lock:
                instances.append((path, instance))

        paths = [f"/tmp/path{i}.jsonl" for i in range(5)]
        threads = [threading.Thread(target=get_instance_with_path, args=(path,)) for path in paths]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Each path should have a unique instance
        path_to_instance = dict(instances)
        assert len(path_to_instance) == 5

        # Instances for different paths should be different
        unique_instances = {id(inst) for _, inst in instances}
        assert len(unique_instances) == 5


class TestProcessedTradeRepositorySingletonFunctionality:
    """Test that singleton instances work correctly."""

    def setup_method(self) -> None:
        ProcessedTradeRepository._instances.clear()

    def teardown_method(self) -> None:
        ProcessedTradeRepository._instances.clear()

    def test_singleton_can_process_trades(self) -> None:
        """Singleton instance should function normally."""
        repo = ProcessedTradeRepository.get_instance()

        key = TradeIdKey(trade_id="test-trade-1")
        assert not repo.is_processed(key)
        assert repo.mark_processed(key) is True
        assert repo.is_processed(key) is True
        # Duplicate should be rejected
        assert repo.mark_processed(key) is False

    def test_different_paths_have_separate_ledgers(self) -> None:
        """Different persistence paths should have separate trade ledgers."""
        import os

        # Clean up persistence files from previous runs
        for path in ["/tmp/ledger1.jsonl", "/tmp/ledger2.jsonl"]:
            ProcessedTradeRepository._instances.pop(path, None)
            if os.path.exists(path):
                os.unlink(path)

        repo1 = ProcessedTradeRepository.get_instance(persistence_path="/tmp/ledger1.jsonl")
        repo2 = ProcessedTradeRepository.get_instance(persistence_path="/tmp/ledger2.jsonl")

        key = TradeIdKey(trade_id="shared-trade-1")

        # Mark in repo1
        assert repo1.mark_processed(key) is True
        assert repo1.is_processed(key) is True

        # repo2 should NOT have this trade (separate ledger)
        assert repo2.is_processed(key) is False

    def test_singleton_with_temp_file(self) -> None:
        """Singleton should work with actual file persistence."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            temp_path = f.name

        try:
            # Clear any existing instance for this path
            ProcessedTradeRepository._instances.pop(temp_path, None)

            repo1 = ProcessedTradeRepository.get_instance(persistence_path=temp_path)
            key = TradeIdKey(trade_id="persistent-trade-1")
            repo1.mark_processed(key)

            # Get the same instance again
            repo2 = ProcessedTradeRepository.get_instance(persistence_path=temp_path)
            assert repo1 is repo2
            assert repo2.is_processed(key) is True
        finally:
            # Cleanup
            ProcessedTradeRepository._instances.pop(temp_path, None)
            Path(temp_path).unlink(missing_ok=True)


class TestProcessedTradeRepositorySingletonRegistry:
    """Test singleton registry management."""

    def setup_method(self) -> None:
        ProcessedTradeRepository._instances.clear()

    def teardown_method(self) -> None:
        ProcessedTradeRepository._instances.clear()

    def test_registry_tracks_instances(self) -> None:
        """Registry should track created instances."""
        assert len(ProcessedTradeRepository._instances) == 0

        ProcessedTradeRepository.get_instance()
        assert len(ProcessedTradeRepository._instances) == 1

        ProcessedTradeRepository.get_instance(persistence_path="/tmp/path1.jsonl")
        assert len(ProcessedTradeRepository._instances) == 2

    def test_registry_keys_are_correct(self) -> None:
        """Registry should use correct keys."""
        ProcessedTradeRepository.get_instance()
        assert "default" in ProcessedTradeRepository._instances

        ProcessedTradeRepository.get_instance(persistence_path="/tmp/custom.jsonl")
        assert "/tmp/custom.jsonl" in ProcessedTradeRepository._instances

    def test_clear_instances(self) -> None:
        """Clearing registry should allow new instances."""
        instance1 = ProcessedTradeRepository.get_instance()
        ProcessedTradeRepository._instances.clear()

        instance2 = ProcessedTradeRepository.get_instance()
        assert instance1 is not instance2


class TestProcessedTradeRepositoryBackwardCompatibility:
    """Test that existing code still works."""

    def setup_method(self) -> None:
        ProcessedTradeRepository._instances.clear()

    def teardown_method(self) -> None:
        ProcessedTradeRepository._instances.clear()

    def test_direct_instantiation_still_works(self) -> None:
        """Old code using ProcessedTradeRepository() directly should work."""
        repo = ProcessedTradeRepository()
        key = TradeIdKey(trade_id="direct-trade-1")
        assert repo.mark_processed(key) is True

    def test_order_manager_with_explicit_repo(self) -> None:
        """OrderManager should accept explicit repository instance."""
        from application.oms.order_manager import OrderManager

        repo = ProcessedTradeRepository()
        om = OrderManager(processed_trade_repository=repo)

        # Should use the provided repo, not a singleton
        assert om.processed_trade_repository is repo

    def test_order_manager_without_repo_creates_default(self) -> None:
        """OrderManager without repo should create a default instance."""
        from application.oms.order_manager import OrderManager

        # Clear any existing default instance
        ProcessedTradeRepository._instances.clear()

        om = OrderManager()
        assert om.processed_trade_repository is not None
        assert isinstance(om.processed_trade_repository, ProcessedTradeRepository)
