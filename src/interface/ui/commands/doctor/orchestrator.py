"""Check orchestrator for parallel execution of diagnostic checks.

Runs independent checks concurrently using ThreadPoolExecutor with
timeout protection and result aggregation.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import TYPE_CHECKING

from interface.ui.commands.doctor.checks import CheckResult

if TYPE_CHECKING:
    from interface.ui.commands.doctor.checks import CheckStrategy
    from interface.ui.services.broker_service import BrokerService

logger = logging.getLogger(__name__)


@dataclass
class SectionResult:
    """Result of a named check section.

    Attributes
    ----------
    section_name : str
        Human-readable section title.
    results : list[CheckResult]
        Check results from this section.
    elapsed_s : float
        Time taken to execute this section.
    """

    section_name: str
    results: list[CheckResult]
    elapsed_s: float = 0.0


class CheckOrchestrator:
    """Orchestrates parallel execution of diagnostic check strategies.

    This class manages a collection of named check strategies, runs them
    concurrently using a thread pool, and aggregates results in a
    thread-safe manner.

    Parameters
    ----------
    checks : list[tuple[str, CheckStrategy]]
        List of (section_name, strategy) tuples defining the checks to run.
    max_workers : int
        Maximum number of parallel threads (default: 4).
    timeout_per_check : int
        Timeout in seconds for each individual check (default: 15).

    Example
    -------
    >>> checks = [
    ...     ("Market Data", MarketDataCheck()),
    ...     ("Order API", OrderAPICheck()),
    ... ]
    >>> orchestrator = CheckOrchestrator(checks, max_workers=4)
    >>> results = orchestrator.run_all(broker_service)
    """

    def __init__(
        self,
        checks: list[tuple[str, CheckStrategy]],
        max_workers: int = 4,
        timeout_per_check: int = 15,
    ) -> None:
        self._checks = checks
        self._max_workers = max_workers
        self._timeout_per_check = timeout_per_check

    def run_all(self, broker_service: BrokerService | None) -> dict[str, SectionResult]:
        """Execute all checks and return aggregated results.

        Parameters
        ----------
        broker_service : BrokerService | None
            The active broker service instance passed to each strategy.

        Returns
        -------
        dict[str, SectionResult]
            Mapping of section name to SectionResult containing the
            check results and execution time.
        """
        results: dict[str, SectionResult] = {}

        def _execute_check(
            section_name: str,
            strategy: CheckStrategy,
        ) -> tuple[str, SectionResult]:
            """Execute a single check with timing and error handling."""
            try:
                start = time.monotonic()
                check_results = strategy.execute(broker_service)
                elapsed = time.monotonic() - start
                logger.info(
                    "doctor_check_completed",
                    extra={"check": section_name, "elapsed_s": round(elapsed, 2)},
                )
                return (section_name, SectionResult(section_name, check_results, elapsed))
            except Exception as exc:
                logger.exception(
                    "doctor_check_failed",
                    extra={"check": section_name, "error": str(exc)},
                )
                elapsed = time.monotonic() - start if "start" in dir() else 0.0
                return (
                    section_name,
                    SectionResult(
                        section_name,
                        [CheckResult(section_name, "ERROR", str(exc))],
                        elapsed,
                    ),
                )

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {
                executor.submit(_execute_check, name, strategy): name
                for name, strategy in self._checks
            }

            for future in as_completed(futures):
                section_name, section_result = future.result(timeout=self._timeout_per_check)
                results[section_name] = section_result

        return results

    @property
    def check_count(self) -> int:
        """Number of check strategies registered."""
        return len(self._checks)
