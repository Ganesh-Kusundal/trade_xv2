"""Tests for Dhan trade/order timestamp parsing.

Guards against silently dropping a valid trade time when Dhan returns the
``DD/MM/YYYY HH:MM:SS`` format (the same quirk that crashed the v2 adapter)
rather than ISO-8601.
"""

from __future__ import annotations

from datetime import datetime

from brokers.providers.dhan.execution.orders import _parse_timestamp


def test_parse_iso8601_timestamp():
    result = _parse_timestamp("2026-06-30T10:15:30+05:30")
    assert isinstance(result, datetime)
    assert result.year == 2026 and result.month == 6 and result.day == 30


def test_parse_dhan_ddmmyyyy_timestamp():
    result = _parse_timestamp("30/06/2026 10:15:30")
    assert isinstance(result, datetime)
    assert (result.year, result.month, result.day) == (2026, 6, 30)
    assert (result.hour, result.minute, result.second) == (10, 15, 30)


def test_parse_junk_returns_none():
    assert _parse_timestamp("not-a-timestamp") is None


def test_parse_empty_returns_none():
    assert _parse_timestamp("") is None
    assert _parse_timestamp(None) is None
