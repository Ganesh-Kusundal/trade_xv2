"""Regression: Dhan segment numeric codes match installed dhanhq SDK."""

from __future__ import annotations

import pytest

from brokers.dhan.segments import DHAN_SDK_SEGMENT_CONSTANTS, NUMERIC_TO_SEGMENT, SEGMENT_TO_NUMERIC


@pytest.mark.parametrize("attr,expected", list(DHAN_SDK_SEGMENT_CONSTANTS.items()))
def test_segment_table_matches_sdk_constant(attr: str, expected: int) -> None:
    try:
        from dhanhq.marketfeed import MarketFeed
    except ImportError:
        pytest.skip("dhanhq SDK not installed")

    sdk_value = getattr(MarketFeed, attr, None)
    assert sdk_value is not None, f"MarketFeed.{attr} missing from installed dhanhq"
    assert sdk_value == expected
    wire = NUMERIC_TO_SEGMENT.get(expected)
    assert wire is not None
    assert SEGMENT_TO_NUMERIC[wire] == expected
