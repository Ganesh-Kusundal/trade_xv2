"""Tests for datalake.schema — canonical schema constants."""

from __future__ import annotations

from datalake.core.schema import (
    ARROW_SCHEMA,
    CANONICAL_COLUMNS,
    HIVE_PARTITION_TEMPLATE,
    OPTIONAL_COLUMNS,
    TEMPORAL_COLUMNS,
    TIMEFRAMES,
    TRADEJ_SCHEMA,
    UNIVERSE_DIR,
    UNIVERSE_FILES,
)


class TestCanonicalColumns:
    def test_required_columns_count(self) -> None:
        assert len(CANONICAL_COLUMNS) == 10

    def test_required_column_names(self) -> None:
        expected = [
            "timestamp",
            "symbol",
            "exchange",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "oi",
            "event_time",
        ]
        assert expected == CANONICAL_COLUMNS

    def test_first_column_is_timestamp(self) -> None:
        assert CANONICAL_COLUMNS[0] == "timestamp"

    def test_ohlcv_present(self) -> None:
        for col in ("open", "high", "low", "close", "volume"):
            assert col in CANONICAL_COLUMNS


class TestOptionalColumns:
    def test_optional_columns(self) -> None:
        assert "vwap" in OPTIONAL_COLUMNS
        assert "trade_count" in OPTIONAL_COLUMNS


class TestArrowSchema:
    def test_field_count(self) -> None:
        assert len(ARROW_SCHEMA) == len(CANONICAL_COLUMNS) + len(TEMPORAL_COLUMNS) - 1  # event_time in both

    def test_field_names_contain_canonical(self) -> None:
        field_names = [f.name for f in ARROW_SCHEMA]
        for col in CANONICAL_COLUMNS:
            assert col in field_names

    def test_field_names_contain_temporal(self) -> None:
        field_names = [f.name for f in ARROW_SCHEMA]
        for col in TEMPORAL_COLUMNS:
            assert col in field_names

    def test_timestamp_is_timestamp_type(self) -> None:
        import pyarrow as pa

        ts_field = ARROW_SCHEMA.field("timestamp")
        assert pa.types.is_timestamp(ts_field.type)

    def test_ohlcv_are_float64(self) -> None:
        import pyarrow as pa

        for col in ("open", "high", "low", "close"):
            assert pa.types.is_float64(ARROW_SCHEMA.field(col).type)

    def test_volume_is_int64(self) -> None:
        import pyarrow as pa

        assert pa.types.is_int64(ARROW_SCHEMA.field("volume").type)

    def test_oi_is_int64(self) -> None:
        import pyarrow as pa

        assert pa.types.is_int64(ARROW_SCHEMA.field("oi").type)


class TestTimeframes:
    def test_supported_timeframes(self) -> None:
        assert "1m" in TIMEFRAMES
        assert "5m" in TIMEFRAMES
        assert "15m" in TIMEFRAMES
        assert "1h" in TIMEFRAMES
        assert "1d" in TIMEFRAMES

    def test_timeframes_is_list(self) -> None:
        assert isinstance(TIMEFRAMES, list)


class TestUniverseFiles:
    def test_all_universes_present(self) -> None:
        assert "NIFTY50" in UNIVERSE_FILES
        assert "NIFTY100" in UNIVERSE_FILES
        assert "NIFTY200" in UNIVERSE_FILES
        assert "NIFTY500" in UNIVERSE_FILES

    def test_paths_are_strings(self) -> None:
        for key, path in UNIVERSE_FILES.items():
            assert isinstance(path, str), f"{key} path is not a string"

    def test_original_paths_contain_universe_dir(self) -> None:
        original_files = {
            "NIFTY50": "data/universes/nifty50.csv",
            "NIFTY100": "data/universes/nifty100.csv",
            "NIFTY200": "data/universes/nifty200.csv",
            "NIFTY500": "data/universes/nifty500.csv",
        }
        for path in original_files.values():
            assert path.startswith(UNIVERSE_DIR)


class TestTradejSchema:
    def test_tradej_schema_mapping(self) -> None:
        assert TRADEJ_SCHEMA["bar_time_ms"] == "timestamp_ms"
        assert TRADEJ_SCHEMA["open_paisa"] == "open_paisa"
        assert TRADEJ_SCHEMA["volume"] == "volume"


class TestHivePartitionTemplate:
    def test_template_contains_placeholders(self) -> None:
        assert "{timeframe}" in HIVE_PARTITION_TEMPLATE
        assert "{symbol}" in HIVE_PARTITION_TEMPLATE

    def test_template_starts_with_equities(self) -> None:
        assert HIVE_PARTITION_TEMPLATE.startswith("equities")
