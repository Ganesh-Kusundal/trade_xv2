"""DataQualityEngine gap detection on timestamp sequences."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from datalake.quality import DataQualityEngine


def test_detect_gaps_finds_missing_interval() -> None:
    engine = DataQualityEngine()
    base = datetime(2024, 1, 15, 9, 15, tzinfo=UTC)
    # 1-minute bars with a hole at +2m
    timestamps = [
        base,
        base + timedelta(minutes=1),
        base + timedelta(minutes=3),
        base + timedelta(minutes=4),
    ]
    gaps = engine.detect_gaps(timestamps, expected_delta=timedelta(minutes=1))
    assert len(gaps) == 1
    assert gaps[0] == (base + timedelta(minutes=1), base + timedelta(minutes=3))


def test_detect_gaps_none_when_contiguous() -> None:
    engine = DataQualityEngine()
    base = datetime(2024, 1, 15, 9, 15, tzinfo=UTC)
    timestamps = [base + timedelta(minutes=i) for i in range(5)]
    assert engine.detect_gaps(timestamps, expected_delta=timedelta(minutes=1)) == []


def test_detect_gaps_empty_input() -> None:
    engine = DataQualityEngine()
    assert engine.detect_gaps([], expected_delta=timedelta(minutes=1)) == []
