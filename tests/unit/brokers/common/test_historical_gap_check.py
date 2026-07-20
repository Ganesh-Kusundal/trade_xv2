"""Unit tests for historical gap-free certification helper."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from brokers.common.historical_gap_check import assert_gap_free_historical


class _Bar:
    def __init__(self, ts: datetime) -> None:
        self.timestamp = ts


class _Series:
    def __init__(self, bars, *, gaps=None, is_degraded=False) -> None:
        self.bars = bars
        self.gaps = gaps or []
        self.is_degraded = is_degraded


@pytest.mark.unit
def test_assert_gap_free_passes_monotonic_bars() -> None:
    bars = [
        _Bar(datetime(2026, 1, 1, tzinfo=timezone.utc)),
        _Bar(datetime(2026, 1, 2, tzinfo=timezone.utc)),
    ]
    assert assert_gap_free_historical(_Series(bars), timeframe="1D") == 2


@pytest.mark.unit
def test_assert_gap_free_fails_on_gaps() -> None:
    with pytest.raises(RuntimeError, match="gaps detected"):
        assert_gap_free_historical(_Series([], gaps=[object()]), timeframe="1m")


@pytest.mark.unit
def test_assert_gap_free_fails_on_non_monotonic() -> None:
    bars = [
        _Bar(datetime(2026, 1, 2, tzinfo=timezone.utc)),
        _Bar(datetime(2026, 1, 1, tzinfo=timezone.utc)),
    ]
    with pytest.raises(RuntimeError, match="non-monotonic"):
        assert_gap_free_historical(_Series(bars), timeframe="1m")
