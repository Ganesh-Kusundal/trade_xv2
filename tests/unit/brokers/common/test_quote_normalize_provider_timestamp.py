"""Provider timestamp preservation in shared quote normalization."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from brokers.common.quote_normalize import normalize_broker_quote
from brokers.common.quote_timestamp import parse_quote_exchange_time
from domain.instruments.instrument_id import InstrumentId


def test_parse_quote_exchange_time_from_dict_keys() -> None:
    tz = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
    ts = datetime(2026, 1, 15, 9, 15, tzinfo=timezone.utc)
    assert parse_quote_exchange_time({"last_traded_time": ts.isoformat()}, tz) == ts
    assert parse_quote_exchange_time({"exchange_timestamp": ts.isoformat()}, tz) == ts
    assert parse_quote_exchange_time({"LTT": ts.isoformat()}, tz) == ts
    assert parse_quote_exchange_time({"timestamp": ts.isoformat()}, tz) == ts


def test_parse_quote_exchange_time_millis_and_object_attribute() -> None:
    tz = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
    expected = datetime(2025, 5, 20, 9, 15, tzinfo=timezone.utc)
    ts_ms = int(expected.timestamp() * 1000)
    assert parse_quote_exchange_time({"exchange_timestamp": ts_ms}, tz) == expected

    class _Tick:
        timestamp = expected

    assert parse_quote_exchange_time(_Tick(), tz) == expected


def test_normalize_broker_quote_sets_provider_timestamp_and_fetched_at() -> None:
    fetched_at = datetime(2026, 1, 15, 10, 0, 1, tzinfo=timezone.utc)
    provider_ts = datetime(2026, 1, 15, 9, 59, 55, tzinfo=timezone.utc)
    iid = InstrumentId.equity("NSE", "RELIANCE")

    snap = normalize_broker_quote(
        {"last_price": "2500", "exchange_timestamp": provider_ts.isoformat()},
        iid,
        broker_id="dhan",
        now=fetched_at,
    )

    assert snap.event_time == provider_ts
    assert snap.provenance.provider_timestamp == provider_ts
    assert snap.provenance.fetched_at == fetched_at


def test_normalize_broker_quote_falls_back_to_fetched_at_without_broker_time() -> None:
    fetched_at = datetime(2026, 1, 15, 10, 0, 1, tzinfo=timezone.utc)
    iid = InstrumentId.equity("NSE", "INFY")

    snap = normalize_broker_quote(
        {"last_price": Decimal("1800")},
        iid,
        broker_id="upstox",
        now=fetched_at,
    )

    assert snap.event_time == fetched_at
    assert snap.provenance.provider_timestamp is None
    assert snap.provenance.fetched_at == fetched_at
