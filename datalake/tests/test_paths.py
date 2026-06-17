"""Tests for :mod:`datalake.paths` (REF-10).

These tests are the regression net for the path consolidation.
If any caller bypasses :func:`symbol_partition_path` and rebuilds
the partition string inline, these tests should still pass — but
a smoke test that walks every datalake reader/writer to check they
import from :mod:`datalake.paths` should be added separately.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from datalake.paths import (
    DEFAULT_DATA_ROOT,
    DEFAULT_TIMEFRAME,
    PARTITION_EXPIRY,
    PARTITION_SYMBOL,
    PARTITION_TIMEFRAME,
    PARTITION_UNDERLYING,
    SUPPORTED_TIMEFRAMES,
    option_partition_path,
    partition_path_to_dict,
    symbol_partition_glob,
    symbol_partition_path,
)


def test_default_root_is_market_data():
    assert DEFAULT_DATA_ROOT == "market_data"


def test_default_timeframe_is_one_minute():
    assert DEFAULT_TIMEFRAME == "1m"


def test_one_minute_is_supported():
    assert "1m" in SUPPORTED_TIMEFRAMES


def test_supported_timeframes_is_immutable():
    # frozenset cannot be mutated. This is a structural check; if
    # someone ``list()``s it and tries to mutate the copy, that is
    # allowed but they should not mutate the module-level constant.
    assert isinstance(SUPPORTED_TIMEFRAMES, frozenset)


def test_symbol_partition_path_default_timeframe():
    assert symbol_partition_path("market_data", "RELIANCE") == Path(
        "market_data/equities/candles/timeframe=1m/symbol=RELIANCE/data.parquet"
    )


def test_symbol_partition_path_explicit_timeframe():
    assert symbol_partition_path("market_data", "TCS", "5m") == Path(
        "market_data/equities/candles/timeframe=5m/symbol=TCS/data.parquet"
    )


def test_symbol_partition_path_rejects_unknown_timeframe():
    with pytest.raises(ValueError, match="unsupported timeframe"):
        symbol_partition_path("market_data", "RELIANCE", "3m")


def test_symbol_partition_glob_matches_all_symbols_for_timeframe():
    assert symbol_partition_glob("market_data", "1m") == (
        "market_data/equities/candles/timeframe=1m/symbol=*/data.parquet"
    )


def test_symbol_partition_glob_rejects_unknown_timeframe():
    with pytest.raises(ValueError, match="unsupported timeframe"):
        symbol_partition_glob("market_data", "9m")


def test_option_partition_path():
    assert option_partition_path("market_data", "2026-06-26", "NIFTY") == Path(
        "market_data/options/chains/expiry=2026-06-26/underlying=NIFTY/data.parquet"
    )


def test_partition_path_to_dict_symbol():
    parsed = partition_path_to_dict(
        "market_data/equities/candles/timeframe=1m/symbol=RELIANCE/data.parquet"
    )
    assert parsed == {"timeframe": "1m", "symbol": "RELIANCE"}


def test_partition_path_to_dict_option():
    parsed = partition_path_to_dict(
        "market_data/options/chains/expiry=2026-06-26/underlying=NIFTY/data.parquet"
    )
    assert parsed == {"expiry": "2026-06-26", "underlying": "NIFTY"}


def test_partition_path_to_dict_ignores_non_partition_segments():
    parsed = partition_path_to_dict(
        "market_data/equities/candles/timeframe=1m/symbol=RELIANCE/data.parquet"
    )
    assert "equities" not in parsed
    assert "candles" not in parsed
    assert "data.parquet" not in parsed


def test_partition_path_to_dict_empty_for_unrelated_path():
    assert partition_path_to_dict("/var/log/syslog") == {}


def test_partition_keys_are_canonical():
    assert PARTITION_TIMEFRAME == "timeframe"
    assert PARTITION_SYMBOL == "symbol"
    assert PARTITION_EXPIRY == "expiry"
    assert PARTITION_UNDERLYING == "underlying"
