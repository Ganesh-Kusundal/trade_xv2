"""Unit tests for domain.parsing."""

from __future__ import annotations

from datetime import datetime, timezone

from domain.candles._helpers import parse_broker_timestamp, parse_datalake_timestamp
from domain.parsing import parse_timestamp


def test_parse_timestamp_epoch_is_utc_aware_not_system_local():
    """Regression: fromtimestamp() without tz= uses the system's local
    timezone, so the same epoch parsed differently depending on where
    the process ran -- on an IST host it silently produced a naive
    value equal to the correct IST wall clock, which downstream code
    (ensure_timestamp_dtype's "naive -> assume already IST" fallback)
    happened to treat correctly by accident; on a UTC host the same
    code produced a naive UTC value that got the same fallback treatment
    and landed 5.5h off. Fix: always resolve epochs to explicit UTC."""
    ts = parse_timestamp(1735780500)  # 2025-01-02 01:15:00 UTC
    assert ts is not None
    assert ts.tzinfo is not None
    assert ts.astimezone(timezone.utc).isoformat() == "2025-01-02T01:15:00+00:00"


def test_parse_timestamp_iso_string_with_offset_preserved():
    ts = parse_timestamp("2026-07-13T09:15:00+05:30")
    assert ts is not None
    assert ts.astimezone(timezone.utc).isoformat() == "2026-07-13T03:45:00+00:00"


def test_parse_timestamp_none_for_empty():
    assert parse_timestamp(None) is None
    assert parse_timestamp("") is None


def test_cross_representation_ist_index_parity():
    """REF-7 zero-parity: the two broker-edge timestamp representations must
    converge to the *same* UTC ``event_time`` through the shared domain
    normalizers, so a bar from Dhan (UTC epoch) and the same bar stored in the
    naive-IST parquet lake land on an identical IST/UTC index.

    NSE open 2024-01-02 09:15 IST == 2024-01-02 03:45 UTC.
    """
    # Dhan edge: epoch → UTC-aware datetime → parse_broker_timestamp.
    dhan_utc_aware = datetime(2024, 1, 2, 3, 45, 0, tzinfo=timezone.utc)
    broker_event_time = parse_broker_timestamp(dhan_utc_aware)

    # Datalake edge: parquet stores the same instant as naive IST wall clock.
    lake_naive_ist = datetime(2024, 1, 2, 9, 15, 0)
    lake_event_time = parse_datalake_timestamp(lake_naive_ist)

    assert broker_event_time == lake_event_time
    assert broker_event_time.astimezone(timezone.utc).isoformat() == "2024-01-02T03:45:00+00:00"
    # Both must be tz-aware UTC — never naive (naive is the silent-5.5h-drift bug).
    assert broker_event_time.tzinfo is not None and lake_event_time.tzinfo is not None
