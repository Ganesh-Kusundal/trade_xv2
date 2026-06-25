"""ScannerRunner — Parallel scanner execution engine.

Runs multiple scanners concurrently using ThreadPoolExecutor,
with error isolation and completion-order result delivery.

Usage
-----
    runner = ScannerRunner(max_workers=4)

    # Run all scanners and collect results
    results = runner.run_all(scanners, universe_df)

    # Stream results as they complete
    for result in runner.run_streaming(scanners, universe_df):
        if result.success:
            print(f"{result.scanner_name}: {result.candidate_count} candidates")
        else:
            print(f"{result.scanner_name} failed: {result.error}")

Thread Safety
-------------
- Each scanner receives a copy of the universe DataFrame
- EventBus is already thread-safe (uses RLock)
- Each scanner has its own FeaturePipeline instance
"""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import pandas as pd

from analytics.scanner.models import Scanner, ScanResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScannerTaskResult:
    """Result of a single scanner execution (success or failure)."""

    scanner_name: str
    success: bool
    scan_result: ScanResult | None = None
    error: str | None = None
    execution_time_ms: float = 0.0

    @property
    def candidate_count(self) -> int:
        """Number of candidates (0 if failed or empty)."""
        if self.scan_result is not None:
            return self.scan_result.count
        return 0

    def to_scan_result(self) -> ScanResult:
        """Convert to ScanResult if successful, raises otherwise."""
        if not self.success or self.scan_result is None:
            raise RuntimeError(f"Scanner '{self.scanner_name}' failed: {self.error}")
        return self.scan_result


@dataclass
class ScannerRunner:
    """Runs multiple scanners in parallel with error isolation.

    The runner accepts a list of Scanner instances and executes them
    concurrently using ThreadPoolExecutor. Results are returned in
    completion order (fastest scanner first).

    Thread Safety
    -------------
    - Each scanner receives a copy of the universe DataFrame to prevent
      concurrent mutation issues
    - EventBus is already thread-safe (uses RLock internally)
    - Each scanner has its own FeaturePipeline instance (no shared state)

    Error Isolation
    ---------------
    - Individual scanner failures are caught and reported as failed results
    - Other scanners continue executing unaffected
    - No exceptions escape from parallel execution

    Attributes
    ----------
    max_workers:
        Maximum number of concurrent scanner threads.
        Defaults to min(4, len(scanners)) if not specified.
    timeout_seconds:
        Optional timeout for entire batch execution.
        None means wait indefinitely.
    """

    max_workers: int | None = None
    timeout_seconds: float | None = None

    def run_all(
        self,
        scanners: list[Scanner],
        universe: pd.DataFrame,
    ) -> list[ScannerTaskResult]:
        """Execute all scanners and return results in completion order.

        Parameters
        ----------
        scanners:
            List of Scanner instances to execute.
        universe:
            Universe DataFrame with OHLCV data for all symbols.

        Returns
        -------
        list[ScannerTaskResult]:
            Results in completion order (fastest first).
            Failed scanners are included with success=False.

        Example
        -------
            scanners = [MomentumScanner(), VolumeScanner(), BreakoutScanner()]
            results = runner.run_all(scanners, universe_df)

            successful = [r for r in results if r.success]
            failed = [r for r in results if not r.success]
        """
        if not scanners:
            return []

        results: list[ScannerTaskResult] = []

        with ThreadPoolExecutor(
            max_workers=self.max_workers or min(4, len(scanners)),
            thread_name_prefix="ScannerRunner",
        ) as executor:
            # Submit all scanner tasks
            future_to_scanner: dict[Future, Scanner] = {}
            for scanner in scanners:
                future = executor.submit(self._execute_scanner, scanner, universe)
                future_to_scanner[future] = scanner

            # Collect results in completion order
            for future in as_completed(future_to_scanner, timeout=self.timeout_seconds):
                scanner = future_to_scanner[future]
                try:
                    task_result = future.result()
                    results.append(task_result)
                except Exception as exc:
                    # Should not happen due to _execute_scanner error handling,
                    # but guard against unexpected executor failures
                    logger.exception(
                        "Unexpected executor error for scanner '%s': %s",
                        scanner.name,
                        exc,
                    )
                    results.append(
                        ScannerTaskResult(
                            scanner_name=scanner.name,
                            success=False,
                            error=f"Executor error: {exc}",
                        )
                    )

        return results

    def run_streaming(
        self,
        scanners: list[Scanner],
        universe: pd.DataFrame,
    ) -> Generator[ScannerTaskResult, None, None]:
        """Execute scanners and yield results as they complete.

        This is a generator that yields ScannerTaskResult instances
        as each scanner finishes, allowing real-time processing.

        Parameters
        ----------
        scanners:
            List of Scanner instances to execute.
        universe:
            Universe DataFrame with OHLCV data for all symbols.

        Yields
        ------
        ScannerTaskResult:
            Results in completion order.

        Example
        -------
            for result in runner.run_streaming(scanners, universe_df):
                if result.success:
                    dashboard.update(result.scan_result)
                else:
                    logger.error("Scanner failed: %s", result.error)
        """
        if not scanners:
            return

        with ThreadPoolExecutor(
            max_workers=self.max_workers or min(4, len(scanners)),
            thread_name_prefix="ScannerRunner",
        ) as executor:
            future_to_scanner: dict[Future, Scanner] = {}
            for scanner in scanners:
                future = executor.submit(self._execute_scanner, scanner, universe)
                future_to_scanner[future] = scanner

            for future in as_completed(future_to_scanner, timeout=self.timeout_seconds):
                scanner = future_to_scanner[future]
                try:
                    task_result = future.result()
                    yield task_result
                except Exception as exc:
                    logger.exception(
                        "Unexpected executor error for scanner '%s': %s",
                        scanner.name,
                        exc,
                    )
                    yield ScannerTaskResult(
                        scanner_name=scanner.name,
                        success=False,
                        error=f"Executor error: {exc}",
                    )

    def run_with_fallback(
        self,
        scanners: list[Scanner],
        universe: pd.DataFrame,
        fallback_scanners: list[Scanner] | None = None,
    ) -> list[ScannerTaskResult]:
        """Execute scanners with fallback on failure.

        If any scanner fails, optionally runs fallback scanners to ensure
        at least some results are returned.

        Parameters
        ----------
        scanners:
            Primary list of scanners to execute.
        universe:
            Universe DataFrame.
        fallback_scanners:
            Optional fallback scanners to run if any primary scanner fails.

        Returns
        -------
        list[ScannerTaskResult]:
            Combined results from primary and fallback scanners.
        """
        results = self.run_all(scanners, universe)

        failed_count = sum(1 for r in results if not r.success)
        if failed_count > 0 and fallback_scanners:
            logger.info(
                "%d scanner(s) failed, running %d fallback scanner(s)",
                failed_count,
                len(fallback_scanners),
            )
            fallback_results = self.run_all(fallback_scanners, universe)
            results.extend(fallback_results)

        return results

    @staticmethod
    def _execute_scanner(
        scanner: Scanner,
        universe: pd.DataFrame,
    ) -> ScannerTaskResult:
        """Execute a single scanner with error isolation.

        This method runs in a separate thread and:
        1. Creates a copy of the universe DataFrame to prevent mutation
        2. Times the execution
        3. Catches all exceptions to isolate failures
        4. Returns a ScannerTaskResult with success/failure status

        Parameters
        ----------
        scanner:
            Scanner instance to execute.
        universe:
            Universe DataFrame (will be copied).

        Returns
        -------
        ScannerTaskResult:
            Execution outcome.
        """
        start_time = time.perf_counter()

        try:
            # Copy DataFrame to prevent concurrent mutation issues
            # Scanners may modify the DataFrame internally
            universe_copy = universe.copy()

            logger.debug(
                "Starting scanner '%s' on %d symbols",
                scanner.name,
                len(universe_copy),
            )

            # Execute scanner
            scan_result = scanner.scan(universe_copy)

            execution_time_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "Scanner '%s' completed: %d candidates in %.0fms",
                scanner.name,
                scan_result.count,
                execution_time_ms,
            )

            return ScannerTaskResult(
                scanner_name=scanner.name,
                success=True,
                scan_result=scan_result,
                execution_time_ms=execution_time_ms,
            )

        except Exception as exc:
            execution_time_ms = (time.perf_counter() - start_time) * 1000

            logger.exception(
                "Scanner '%s' failed after %.0fms: %s",
                scanner.name,
                execution_time_ms,
                exc,
            )

            return ScannerTaskResult(
                scanner_name=scanner.name,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                execution_time_ms=execution_time_ms,
            )


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------


def run_scanners_parallel(
    scanners: list[Scanner],
    universe: pd.DataFrame,
    max_workers: int | None = None,
    timeout_seconds: float | None = None,
) -> list[ScanResult]:
    """Convenience function to run scanners in parallel.

    Returns only successful ScanResult instances (failures are logged).

    Parameters
    ----------
    scanners:
        List of Scanner instances.
    universe:
        Universe DataFrame.
    max_workers:
        Maximum concurrent threads (default: min(4, len(scanners))).
    timeout_seconds:
        Optional timeout for entire batch.

    Returns
    -------
    list[ScanResult]:
        Successful ScanResult instances.

    Example
    -------
        from analytics.scanner import MomentumScanner, VolumeScanner

        scanners = [MomentumScanner(), VolumeScanner()]
        results = run_scanners_parallel(scanners, universe_df)

        for result in results:
            print(f"{result.scanner}: {result.count} candidates")
    """
    runner = ScannerRunner(
        max_workers=max_workers,
        timeout_seconds=timeout_seconds,
    )
    task_results = runner.run_all(scanners, universe)

    successful_results: list[ScanResult] = []
    for task_result in task_results:
        if task_result.success and task_result.scan_result is not None:
            successful_results.append(task_result.scan_result)
        else:
            logger.warning(
                "Scanner '%s' failed: %s",
                task_result.scanner_name,
                task_result.error,
            )

    return successful_results


def run_scanners_with_timing(
    scanners: list[Scanner],
    universe: pd.DataFrame,
    max_workers: int | None = None,
) -> tuple[list[ScanResult], dict[str, float]]:
    """Run scanners in parallel and return results with timing info.

    Parameters
    ----------
    scanners:
        List of Scanner instances.
    universe:
        Universe DataFrame.
    max_workers:
        Maximum concurrent threads.

    Returns
    -------
    tuple[list[ScanResult], dict[str, float]]:
        Tuple of (successful ScanResults, timing dict {scanner_name: ms}).
    """
    runner = ScannerRunner(max_workers=max_workers)
    task_results = runner.run_all(scanners, universe)

    successful_results: list[ScanResult] = []
    timing: dict[str, float] = {}

    for task_result in task_results:
        timing[task_result.scanner_name] = task_result.execution_time_ms

        if task_result.success and task_result.scan_result is not None:
            successful_results.append(task_result.scan_result)

    return successful_results, timing


__all__ = [
    "ScannerRunner",
    "ScannerTaskResult",
    "run_scanners_parallel",
    "run_scanners_with_timing",
]
