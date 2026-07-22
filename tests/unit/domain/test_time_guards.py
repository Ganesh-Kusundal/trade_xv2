"""Unit tests for require_tz_aware helper."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from domain.parsing import require_tz_aware


def test_require_tz_aware_accepts_aware_datetime() -> None:
    require_tz_aware(datetime(2024, 1, 1, tzinfo=timezone.utc), "should not raise")


def test_require_tz_aware_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="must be timezone-aware"):
        require_tz_aware(datetime(2024, 1, 1), "must be timezone-aware")
