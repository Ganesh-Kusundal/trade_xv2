"""Pytest fixtures for the Dhan instrument resolution test suite.

These fixtures point the ``InstrumentService`` at the **real, committed
Dhan master CSV** (see ``brokers/dhan/tests/fixtures/instruments/README.md``).
No mocks, no synthetic data — the tests exercise the same code path
that production callers use.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from brokers.dhan.instrument_service import InstrumentService

# Path to the committed real fixture CSV.  Resolved at import time so
# the conftest errors out loudly if the fixture is missing.
FIXTURE_DIR = Path(__file__).resolve().parent / "instruments"
FIXTURE_CSV = FIXTURE_DIR / "api-scrip-master-minimal.csv"


@pytest.fixture(scope="session")
def real_csv_path() -> Path:
    """Return the absolute path to the committed Dhan master fixture.

    The fixture file is a real, freshly downloaded copy of
    ``https://images.dhan.co/api-data/api-scrip-master.csv`` (truncated
    to fit under the 10 MB repository cap; see the README in
    ``instruments/`` for details).
    """
    if not FIXTURE_CSV.exists():
        raise FileNotFoundError(
            f"Missing Dhan instrument fixture: {FIXTURE_CSV}. "
            "Re-download it with:\n"
            '  python -c "import urllib.request; '
            "urllib.request.urlretrieve("
            "'https://images.dhan.co/api-data/api-scrip-master.csv', "
            f"'{FIXTURE_CSV}')\""
        )
    return FIXTURE_CSV


@pytest.fixture(scope="module")
def instrument_service(real_csv_path) -> InstrumentService:
    """Module-scoped ``InstrumentService`` pointed at the real fixture.

    The service is constructed against a per-module temp directory
    and the catalog is loaded from the committed CSV **once** for the
    whole test module.  The Dhan catalog's ``replace_all`` is
    O(n²)-shaped (plan §10 R1) and takes ~10 s for our 17 628-row
    fixture; re-loading it per test would be untenable.

    Tests that need a fresh service (e.g. to toggle
    ``strict_resolution``) should construct their own
    :class:`InstrumentService` directly via :func:`real_csv_path`.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        service = InstrumentService(cache_dir=Path(td))
        service.load_snapshot(real_csv_path)
        yield service
