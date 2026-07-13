"""Tests for datalake.core.schema.enforce_canonical_schema.

Regression guard for a real bug: two independent datalake writers
(equities/indices via ingestion/loader.py, options via
ingestion/sync_options.py) produced different physical Parquet
timestamp units -- `us` and `ms` respectively -- because neither ever
applied the documented ARROW_SCHEMA. enforce_canonical_schema() is the
single choke point both writers now call before atomic_parquet_write,
so this file tests that function directly rather than each call site.
"""

from __future__ import annotations

from datetime import datetime

import pyarrow as pa

from datalake.core.schema import ARROW_SCHEMA, enforce_canonical_schema


class TestEnforceCanonicalSchema:
    def test_ms_timestamp_upcast_to_us(self):
        table = pa.table(
            {
                "timestamp": pa.array([datetime(2026, 7, 13, 9, 15, 0)], type=pa.timestamp("ms")),
                "symbol": ["NIFTY"],
            }
        )
        result = enforce_canonical_schema(table)
        assert result.schema.field("timestamp").type == pa.timestamp("us")

    def test_ns_timestamp_downcast_to_us(self):
        table = pa.table(
            {
                "timestamp": pa.array([datetime(2026, 7, 13, 9, 15, 0)], type=pa.timestamp("ns")),
                "symbol": ["NIFTY"],
            }
        )
        result = enforce_canonical_schema(table)
        assert result.schema.field("timestamp").type == pa.timestamp("us")

    def test_value_preserved_across_unit_cast(self):
        """Cast must not silently truncate or shift the actual instant."""
        ts = datetime(2026, 7, 13, 9, 15, 30, 123000)  # exact microsecond value
        table = pa.table({"timestamp": pa.array([ts], type=pa.timestamp("ms"))})
        result = enforce_canonical_schema(table)
        assert result.column("timestamp")[0].as_py() == ts

    def test_already_correct_unit_is_a_noop(self):
        table = pa.table(
            {
                "timestamp": pa.array([datetime(2026, 7, 13, 9, 15, 0)], type=pa.timestamp("us")),
                "symbol": ["NIFTY"],
            }
        )
        result = enforce_canonical_schema(table)
        assert result is table, "no cast needed -- must return the same object, not a copy"

    def test_unknown_extra_columns_pass_through_unchanged(self):
        table = pa.table(
            {
                "timestamp": pa.array([datetime(2026, 7, 13, 9, 15, 0)], type=pa.timestamp("ms")),
                "some_new_column": [42],
            }
        )
        result = enforce_canonical_schema(table)
        assert result.schema.field("some_new_column").type == pa.int64()
        assert result.column("some_new_column")[0].as_py() == 42

    def test_non_timestamp_columns_untouched(self):
        table = pa.table(
            {
                "timestamp": pa.array([datetime(2026, 7, 13, 9, 15, 0)], type=pa.timestamp("ms")),
                "symbol": ["NIFTY"],
                "open": [100.5],
            }
        )
        result = enforce_canonical_schema(table)
        assert result.schema.field("symbol").type == pa.utf8()
        assert result.schema.field("open").type == pa.float64()

    def test_multiple_timestamp_columns_all_cast(self):
        """event_time/published_at/ingested_at are also declared timestamps
        in ARROW_SCHEMA and must be cast alongside the primary timestamp."""
        table = pa.table(
            {
                "timestamp": pa.array([datetime(2026, 7, 13, 9, 15, 0)], type=pa.timestamp("ms")),
                "event_time": pa.array([datetime(2026, 7, 13, 9, 15, 0)], type=pa.timestamp("ns")),
            }
        )
        result = enforce_canonical_schema(table)
        assert result.schema.field("timestamp").type == pa.timestamp("us")
        assert result.schema.field("event_time").type == pa.timestamp("us")

    def test_arrow_schema_declares_microsecond_timestamps(self):
        """ARROW_SCHEMA itself must declare `us`, matching what writers
        actually produce -- the original bug was ARROW_SCHEMA saying `ns`
        while nothing enforced it and every writer produced us/ms."""
        for field in ARROW_SCHEMA:
            if pa.types.is_timestamp(field.type):
                assert field.type == pa.timestamp("us"), (
                    f"{field.name} declared as {field.type}, expected timestamp[us]"
                )
