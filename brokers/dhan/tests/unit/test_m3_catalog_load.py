"""M3 regression tests — Catalog, broker, and resolver migration.

Verifies the contract for M3 deliverables:

* F11 (catalog.load_from_daily_cache) — the method now populates the
  indexes (previously it dropped the parsed list on the floor).
* M3 call-site migration — the InstrumentService path is wired into
  DhanBroker (next: we will pin every resolve_security_id call site
  here, but the most important is the F11 fix, which is the load-path
  half of M3).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from brokers.dhan.mapper.instruments import DhanInstrumentCatalog

pytestmark = pytest.mark.unit


class TestCatalogLoadFromDailyCache:
    """F11 regression: ``DhanInstrumentCatalog.load_from_daily_cache`` must
    build the in-memory indexes, not just store the snapshot path.

    Pre-fix behaviour (the bug we are guarding against):
        snapshot = catalog.load_from_daily_cache(cache_dir)
        # catalog.size == 0   <-- the loader's parsed list was thrown away
        # catalog.get_by_security_id("2885") is None

    Post-fix behaviour:
        snapshot = catalog.load_from_daily_cache(cache_dir)
        # catalog.is_loaded is True
        # catalog.size > 0
        # catalog.get_by_security_id("2885") is the RELIANCE definition
    """

    def test_load_from_daily_cache_populates_indexes(
        self, real_csv_path: Path, tmp_path: Path
    ) -> None:
        """A load_from_daily_cache call must yield a populated catalog.

        We copy the committed fixture into a fresh cache dir, then point a
        fresh ``DhanInstrumentCatalog`` at it.  Pre-fix, ``size`` was 0;
        post-fix, ``size`` > 0 and the seed SIDs are resolvable.
        """
        # Stage the fixture as "today's snapshot" inside an isolated cache dir.
        cache_dir = tmp_path / "instr_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        import shutil
        from datetime import date

        staged_snapshot = cache_dir / f"api-scrip-master-{date.today()}.csv"
        shutil.copy2(real_csv_path, staged_snapshot)

        # Don't redownload — point the loader at our staged fixture.
        catalog = DhanInstrumentCatalog()
        with patch.object(
            catalog._loader,
            "ensure_daily_snapshot",
            return_value=staged_snapshot,
        ):
            catalog.load_from_daily_cache(cache_dir)

        assert catalog.is_loaded, (
            "load_from_daily_cache must set is_loaded=True after a successful load"
        )
        assert catalog.size > 0, (
            f"Catalog size must be > 0 after load_from_daily_cache; got {catalog.size}. "
            "This is the F11 regression — the loader's parsed list was being dropped."
        )
        # Spot-check the two seed SIDs we know are in the fixture.
        reliance = catalog.get_by_security_id("2885")
        assert reliance is not None, (
            "RELIANCE (sid=2885) must resolve after load_from_daily_cache; "
            "this is the symptom of F11."
        )
        assert reliance.symbol == "RELIANCE"

    def test_load_from_daily_cache_returns_snapshot_path(
        self, real_csv_path: Path, tmp_path: Path
    ) -> None:
        """last_loaded_path must be set after load_from_daily_cache."""
        cache_dir = tmp_path / "instr_cache2"
        cache_dir.mkdir(parents=True, exist_ok=True)
        import shutil
        from datetime import date

        staged_snapshot = cache_dir / f"api-scrip-master-{date.today()}.csv"
        shutil.copy2(real_csv_path, staged_snapshot)

        catalog = DhanInstrumentCatalog()
        with patch.object(
            catalog._loader,
            "ensure_daily_snapshot",
            return_value=staged_snapshot,
        ):
            catalog.load_from_daily_cache(cache_dir)

        assert catalog.last_loaded_path is not None
        assert catalog.last_loaded_path == staged_snapshot
