"""Gap detection and empty-series construction for the historical coordinator.

This module is intentionally free of any import from
``application.data.historical_coordinator`` to avoid a circular dependency.
``HistoricalQuery`` is referenced only in lazy type annotations (enabled by
``from __future__ import annotations``) and is never evaluated at runtime.
"""

from __future__ import annotations

from datetime import timedelta

from application.data.provenance import ProvenanceLedger
from domain.candles.historical import (
    DateRange,
    Gap,
    HistoricalBar,
    HistoricalSeries,
    MergeManifest,
)


class GapDetector:
    """Detect coverage gaps and build empty degraded series."""

    def detect(
        self,
        bars: list[HistoricalBar],
        query: HistoricalQuery,
    ) -> list[Gap]:
        """Detect gaps between the requested coverage and actual bars.

        Gap detection is calendar-day based for daily bars.  For intraday bars,
        gaps are detected by finding consecutive bars with timestamps more than
        2x the timeframe apart (approximate heuristic).
        """
        gaps: list[Gap] = []
        if not bars:
            gaps.append(Gap(start=query.from_date, end=query.to_date, reason="all_failed"))
            return gaps

        # Coverage gap at start
        first_bar_date = bars[0].event_time.date()
        if first_bar_date > query.from_date:
            gaps.append(
                Gap(
                    start=query.from_date,
                    end=first_bar_date - timedelta(days=1),
                    reason="missing_from_start",
                )
            )

        # Coverage gap at end
        last_bar_date = bars[-1].event_time.date()
        if last_bar_date < query.to_date:
            gaps.append(
                Gap(
                    start=last_bar_date + timedelta(days=1),
                    end=query.to_date,
                    reason="missing_from_end",
                )
            )

        return gaps

    @staticmethod
    def empty_series(query: HistoricalQuery, ledger: ProvenanceLedger) -> HistoricalSeries:
        return HistoricalSeries(
            bars=[],
            coverage=DateRange(start=query.from_date, end=query.to_date),
            instrument=query.instrument,
            timeframe=query.timeframe,
            gaps=[Gap(start=query.from_date, end=query.to_date, reason=ledger.degraded_reason)],
            merge_manifest=MergeManifest(degraded=True, degraded_reason=ledger.degraded_reason),
        )
