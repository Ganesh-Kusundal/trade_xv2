"""Unit tests for segment constant mappings."""

from brokers.dhan.domain import Exchange
from brokers.dhan.segments import (
    EXCHANGE_TO_SEGMENT,
    SEGMENT_TO_EXCHANGE,
    NUMERIC_TO_SEGMENT,
    _COMPACT_SEGMENT_MAP,
)


def test_exchange_to_segment_completeness():
    all_exchanges = {e.value for e in Exchange}
    mapped = set(EXCHANGE_TO_SEGMENT.keys())
    assert all_exchanges == mapped, (
        f"Missing mappings for: {all_exchanges - mapped}"
    )


def test_reverse_mapping_consistency():
    for exch, segment in EXCHANGE_TO_SEGMENT.items():
        assert SEGMENT_TO_EXCHANGE[segment] == exch, (
            f"Reverse mismatch: {segment} -> {SEGMENT_TO_EXCHANGE[segment]} != {exch}"
        )


def test_compact_segment_map_has_mcx():
    assert _COMPACT_SEGMENT_MAP[("MCX", "M")] == "MCX_COMM"


def test_numeric_segment_codes():
    assert NUMERIC_TO_SEGMENT[0] == "IDX_I"
    assert NUMERIC_TO_SEGMENT[1] == "NSE_EQ"
    assert NUMERIC_TO_SEGMENT[2] == "NSE_FNO"
    assert NUMERIC_TO_SEGMENT[3] == "NSE_CURRENCY"
    assert NUMERIC_TO_SEGMENT[4] == "BSE_EQ"
    assert NUMERIC_TO_SEGMENT[5] == "MCX_COMM"
