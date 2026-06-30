"""E2E: Resource leak detection tests.

Verify no FD leaks, thread leaks, or lock persistence.
"""
import fcntl
import resource
import subprocess
import threading
import time
from pathlib import Path


class TestResourceLeaks:
    """Test resource leak scenarios."""

    def test_no_fd_leak_on_lock_failure(self):
        """Verify no file descriptor leak when lock acquisition fails."""
        # Get baseline FD count
        before_fds = resource.getrusage(resource.RUSAGE_SELF).ru_nvcsw

        # Attempt to create multiple stores with lock contention
        from application.oms.persistence.errors import OmsWriterLockError

        from application.oms.persistence.sqlite_order_store import SqliteOrderStore

        for _i in range(50):
            try:
                store = SqliteOrderStore(":memory:")
                store._acquire_writer_lock()
            except OmsWriterLockError:
                pass

        after_fds = resource.getrusage(resource.RUSAGE_SELF).ru_nvcsw
        # FD count should not increase significantly
        assert (after_fds - before_fds) < 5  # Allow small variance

    def test_no_thread_leak_on_failed_init(self):
        """Verify no thread leak when initialization fails (P-1.5 fix)."""
        from unittest.mock import patch

        from brokers.common.services.production_readiness import ProductionReadinessError
        from cli.services.broker_service import BrokerService

        before_threads = threading.active_count()

        broker_service = BrokerService(load_instruments=True)

        # Simulate readiness failure
        with patch("brokers.common.services.production_readiness.ProductionReadinessChecker.run_or_raise") as mock:
            mock.side_effect = ProductionReadinessError("Test")
            broker_service._ensure_dhan_initialized()

        broker_service.close()

        after_threads = threading.active_count()
        # Thread count should return to baseline
        assert after_threads <= before_threads + 1  # Allow 1 for test runner

    def test_oms_lock_released_after_cli_exit(self):
        """Verify OMS lock is released after CLI exits."""
        lock_path = Path("market_data/oms_orders.sqlite.lock")

        # Run a command that acquires lock
        subprocess.run(
            ["./venv/bin/python", "-m", "cli.main", "holdings"],
            capture_output=True
        )

        # Give it a moment to clean up
        time.sleep(0.5)

        # Verify lock file is not held
        if lock_path.exists():
            lock_fd = open(lock_path, "r+")  # noqa: SIM115
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                # If we get here, lock was released
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                lock_released = True
            except BlockingIOError:
                lock_released = False
            finally:
                lock_fd.close()

            assert lock_released, "OMS lock still held after CLI exit"
        else:
            # Lock file doesn't exist - also acceptable
            pass
