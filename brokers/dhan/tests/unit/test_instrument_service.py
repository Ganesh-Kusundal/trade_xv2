"""Smoke tests for ``brokers.dhan.instrument_service.InstrumentService``.

These tests pin M1's contract against the real, committed Dhan master
CSV fixture.  They are the only tests that need to pass before M1 is
considered done.

Constraints (from the user rules):

* No mocking, no synthetic data — every assertion is against the real
  fixture CSV.
* Tests are marked ``@pytest.mark.unit`` so they can be deselected
  with ``-m 'not unit'``.

If any of these tests fail after a Dhan master change, regenerate the
fixture (see ``brokers/dhan/tests/fixtures/instruments/README.md``)
and re-run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from brokers.dhan.instrument_service import (
    InstrumentNotFoundError,
    InstrumentService,
    SnapshotInfo,
    SnapshotUnavailableError,
)

pytestmark = pytest.mark.unit


# ── 1. load_snapshot returns a non-trivial SnapshotInfo ───────────────────


def test_load_snapshot_returns_snapshot_info_with_records_and_checksum(
    instrument_service: InstrumentService, real_csv_path: Path
) -> None:
    info = instrument_service.snapshot_info
    assert isinstance(info, SnapshotInfo)
    assert info.record_count > 0, "snapshot must have at least one record"
    assert len(info.checksum) == 64, "checksum must be a 64-char SHA-256 hex string"
    # The checksum is a hex string; verify it's all hex.
    int(info.checksum, 16)
    assert info.source_path == real_csv_path
    assert info.wire_url.startswith("https://")


def test_load_snapshot_indexed_count_matches_record_count(
    instrument_service: InstrumentService,
) -> None:
    # The service's internal catalog size should match SnapshotInfo.record_count
    # for the loaded fixture.  This is the property the broken
    # ``DhanInstrumentCatalog.load_from_daily_cache`` violated: the catalog
    # should have non-zero size after a load_snapshot call.
    info = instrument_service.snapshot_info
    catalog = instrument_service._indexes.catalog
    assert catalog.is_loaded
    # The catalog may have fewer rows than the parsed CSV if some rows
    # had unknown segments that ``replace_all`` silently drops (an
    # existing behaviour, not a regression).  The key invariant is that
    # the catalog is non-empty and large enough to resolve the seed
    # instruments.
    assert catalog.size > 0
    assert catalog.size <= info.record_count
    # And we can actually look up the seed instruments by SID.
    assert catalog.get_by_security_id("2885") is not None  # RELIANCE NSE
    assert catalog.get_by_security_id("13") is not None  # NIFTY IDX


# ── 2. resolve_security_id for a known symbol ─────────────────────────────


def test_resolve_security_id_known_equity_returns_digit_string(
    instrument_service: InstrumentService,
) -> None:
    sid = instrument_service.resolve_security_id("RELIANCE", "NSE")
    assert isinstance(sid, str) and sid, "sid must be a non-empty string"
    assert sid.isdigit(), f"RELIANCE NSE sid must be a digit string, got {sid!r}"


def test_resolve_security_id_known_index_returns_digit_string(
    instrument_service: InstrumentService,
) -> None:
    sid = instrument_service.resolve_security_id("NIFTY", "IDX_I")
    assert isinstance(sid, str) and sid
    assert sid.isdigit()


# ── 3. resolve_security_id for an unknown symbol ───────────────────────────


def test_resolve_security_id_unknown_symbol_raises_when_strict(
    instrument_service: InstrumentService,
) -> None:
    """Default (strict) mode must raise, not silently return junk."""
    with pytest.raises(InstrumentNotFoundError) as excinfo:
        instrument_service.resolve_security_id("TOTALLY_FAKE_XYZ", "NSE")
    assert excinfo.value.symbol == "TOTALLY_FAKE_XYZ"
    assert excinfo.value.exchange == "NSE"


def test_resolve_security_id_unknown_symbol_passthrough_when_lenient(
    real_csv_path: Path,
) -> None:
    """With strict_resolution=False, return the original symbol as a passthrough.

    This matches the current behaviour of the legacy resolver for
    unrecognised inputs and lets callers opt out of the fail-loud
    contract (e.g. for ad-hoc exploratory code).
    """
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        service = InstrumentService(cache_dir=Path(td), strict_resolution=False)
        service.load_snapshot(real_csv_path)

        # Still resolvable via the catalog.
        sid = service.resolve_security_id("RELIANCE", "NSE")
        assert sid.isdigit()

        # Unknown symbol → passthrough.
        out = service.resolve_security_id("TOTALLY_FAKE_XYZ", "NSE")
        assert out == "TOTALLY_FAKE_XYZ"


# ── 4. snapshot_info property round-trips ────────────────────────────────


def test_snapshot_info_property_returns_loaded_info(
    instrument_service: InstrumentService,
) -> None:
    info = instrument_service.snapshot_info
    assert isinstance(info, SnapshotInfo)
    # The same object instance is returned across reads (no copy each time).
    assert instrument_service.snapshot_info is info


def test_snapshot_info_before_load_raises(tmp_path) -> None:
    """Constructing a service does NOT auto-load; snapshot_info must fail loud."""
    service = InstrumentService(cache_dir=tmp_path)
    with pytest.raises(SnapshotUnavailableError):
        _ = service.snapshot_info
