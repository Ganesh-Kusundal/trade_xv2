"""Scanner service for executing scanner runs.

Extracts scanner orchestration logic from API route handlers into
testable services.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanResult:
    scan_id: str
    scanner: str
    universe: str
    candidate_count: int
    timestamp: str


@dataclass(frozen=True)
class ScanRunResult:
    status: str
    results: list[ScanResult]
    scan_ids: list[str]
    universe_stats: dict[str, Any]


class ScannerService:
    """Service for executing scanner runs.

    Encapsulates scanner pipeline construction, universe loading,
    and result persistence that was previously in API route handlers.
    """

    def __init__(
        self,
        datalake_gateway: Any,
        data_catalog: Any,
        event_bus: Any | None = None,
    ) -> None:
        self._gateway = datalake_gateway
        self._catalog = data_catalog
        self._event_bus = event_bus

    def run_scan(
        self,
        scanner_name: str,
        universe: str = "NIFTY500",
    ) -> ScanRunResult:
        """Execute a scanner run.

        Parameters
        ----------
        scanner_name : str
            Name of scanner to run (momentum, volume, breakout).
        universe : str
            Universe to scan (NIFTY50, NIFTY100, etc.).

        Returns
        -------
        ScanRunResult
            Results of the scan execution.
        """
        from analytics.pipeline.pipeline import FeaturePipeline
        from analytics.scanner import BreakoutScanner, MomentumScanner, VolumeScanner
        from analytics.scanner.runner import ScannerRunner
        from datalake.scanner_universe import load_scanner_universe

        pipeline = FeaturePipeline()

        scanner_map = {
            "momentum": lambda: MomentumScanner(pipeline, event_bus=self._event_bus),
            "volume": lambda: VolumeScanner(pipeline, event_bus=self._event_bus),
            "breakout": lambda: BreakoutScanner(pipeline, event_bus=self._event_bus),
        }

        if scanner_name.lower() not in scanner_map:
            raise ValueError(
                f"Unknown scanner '{scanner_name}'. Available: {', '.join(scanner_map.keys())}"
            )

        scanners = [scanner_map[scanner_name.lower()]()]

        universe_df, load_stats = load_scanner_universe(
            self._gateway,
            self._catalog,
            universe,
            timeframe="1m",
        )

        if universe_df.empty:
            raise ValueError(
                f"Universe data not available for '{universe}'. "
                f"requested={load_stats['requested']} loaded={load_stats['loaded']}"
            )

        runner = ScannerRunner(max_workers=4, timeout_seconds=30.0)
        results = runner.run_all(scanners, universe_df)

        scan_results = []
        scan_ids = []
        for result in results:
            if result.success and result.scan_result:
                from analytics.scanner import save_scan_result

                scan_id = save_scan_result(
                    scanner=result.scanner_name,
                    candidates=result.scan_result.candidates,
                    universe_size=result.scan_result.universe_size,
                    metadata={
                        "universe": universe,
                        "load_stats": load_stats,
                    },
                )
                scan_ids.append(scan_id)
                scan_results.append(ScanResult(
                    scan_id=scan_id,
                    scanner=result.scanner_name,
                    universe=universe,
                    candidate_count=result.candidate_count,
                    timestamp=datetime.now().isoformat(),
                ))

        if not scan_ids:
            raise ValueError("Scanner execution failed to produce results")

        return ScanRunResult(
            status="completed",
            results=scan_results,
            scan_ids=scan_ids,
            universe_stats=load_stats,
        )
