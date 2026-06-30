"""E2E: Lock contention tests.

Verify read-only commands work when OMS lock is held.
"""
import concurrent.futures
import fcntl
import subprocess
from pathlib import Path

from rich.console import Console


class TestLockContention:
    """Test OMS lock contention scenarios."""

    def test_quote_works_with_oms_lock_held(self):
        """Verify quote command works even when OMS lock is held."""
        from cli.main import main

        # Acquire OMS lock
        lock_path = Path("market_data/oms_orders.sqlite.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = open(lock_path, "w")  # noqa: SIM115
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        try:
            # Run quote command
            console = Console(force_terminal=True)
            result = main(["quote", "RELIANCE", "--json"], console=console)

            # Should succeed
            assert result["success"] is True
        finally:
            # Release lock
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            lock_fd.close()

    def test_multiple_quotes_in_parallel(self):
        """Verify multiple quote commands run in parallel without lock contention."""

        def run_quote(symbol):
            result = subprocess.run(
                ["./venv/bin/python", "-m", "cli.main", "quote", symbol, "--json"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0

        # Run 5 quotes in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(run_quote, sym) for sym in
                      ["RELIANCE", "TCS", "INFY", "HDFC", "ICICI"]]

            # All should succeed
            results = [f.result() for f in futures]
            assert all(results), f"Some quote commands failed: {results}"
