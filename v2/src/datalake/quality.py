"""Data quality — timestamp gap detection.

ponytail: only gap detection for Phase 5; OHLCV/volume checks later.
"""

from __future__ import annotations

from datetime import datetime, timedelta


class DataQualityEngine:
    """Detect gaps in ordered timestamp sequences."""

    def detect_gaps(
        self,
        timestamps: list[datetime],
        expected_delta: timedelta,
    ) -> list[tuple[datetime, datetime]]:
        if len(timestamps) < 2:
            return []
        ordered = sorted(timestamps)
        gaps: list[tuple[datetime, datetime]] = []
        for prev, cur in zip(ordered, ordered[1:], strict=False):
            if cur - prev > expected_delta:
                gaps.append((prev, cur))
        return gaps
