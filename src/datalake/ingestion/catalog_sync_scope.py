"""Catalog-gated sync scope — datalake only syncs what DuckDB knows about.

The federation/market layer can fetch any instrument live; the datalake sync
pipelines must not attempt symbols or option groups that are not registered in
``catalog.duckdb``. Future additions: register in catalog (or materialize
options groups) first, then sync picks them up on the next run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from datalake.core.symbols import normalize_symbol_for_storage
from datalake.storage.catalog import DataCatalog
from domain.ports.data_catalog import DEFAULT_DATA_PATHS

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CatalogOptionGroup:
    underlying: str
    expiry_kind: str
    expiry_code: int


def list_catalog_symbols(
    lake_root: str | None = None, *, timeframe: str = "1m"
) -> frozenset[str]:
    """Symbols registered in DuckDB ``symbols`` table."""
    root = lake_root or DEFAULT_DATA_PATHS.lake_root
    try:
        catalog = DataCatalog(root, read_only=True)
        return frozenset(catalog.list_symbols(timeframe))
    except Exception as exc:
        logger.warning("catalog_sync_scope: could not list symbols: %s", exc)
        return frozenset()


def list_catalog_option_groups(lake_root: str | None = None) -> list[CatalogOptionGroup]:
    """Option groups present in DuckDB (``m_pcr``), else on-disk ``options/candles/``."""
    root = Path(lake_root or DEFAULT_DATA_PATHS.lake_root)
    db_path = root / "catalog.duckdb"
    if db_path.exists():
        try:
            from datalake.core.duckdb_utils import duckdb_connection

            with duckdb_connection(db_path, read_only=True) as conn:
                has_pcr = conn.execute(
                    """
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_schema = 'main' AND table_name = 'm_pcr'
                    """
                ).fetchone()[0]
                if has_pcr:
                    rows = conn.execute(
                        """
                        SELECT DISTINCT underlying, expiry_kind, expiry_code
                        FROM m_pcr
                        ORDER BY underlying, expiry_kind, expiry_code
                        """
                    ).fetchall()
                    if rows:
                        return [
                            CatalogOptionGroup(
                                normalize_symbol_for_storage(str(r[0])),
                                str(r[1]).upper(),
                                int(r[2]),
                            )
                            for r in rows
                        ]
        except Exception as exc:
            logger.warning("catalog_sync_scope: m_pcr read failed: %s", exc)
    return _option_groups_from_disk(root)


def _option_groups_from_disk(root: Path) -> list[CatalogOptionGroup]:
    """Fallback when m_pcr not materialized — infer from legacy rolling parquet dirs."""
    candles = root / "options" / "candles"
    if not candles.exists():
        return []
    out: list[CatalogOptionGroup] = []
    for udir in sorted(candles.glob("underlying=*")):
        underlying = udir.name.split("=", 1)[1]
        for edir in udir.glob("expiry_kind=*"):
            ek = edir.name.split("=", 1)[1].upper()
            for cdir in edir.glob("expiry_code=*"):
                ec = int(cdir.name.split("=", 1)[1])
                if (cdir / "data.parquet").exists():
                    out.append(CatalogOptionGroup(underlying, ek, ec))
    return out


def gate_equity_sync_entries(entries, catalog_symbols: frozenset[str]):
    """Return (eligible, skipped_symbols). Manifest intent ∩ catalog registration."""
    if not catalog_symbols:
        logger.info("catalog_gate: empty symbols table — syncing all manifest entries")
        return entries, []
    eligible = []
    skipped: list[str] = []
    for entry in entries:
        if entry.symbol in catalog_symbols:
            eligible.append(entry)
        else:
            skipped.append(entry.symbol)
    if skipped:
        logger.info(
            "catalog_gate: skipped %d manifest symbols not in DuckDB catalog",
            len(skipped),
        )
    return eligible, skipped


def gate_options_sync_entries(entries, groups: list[CatalogOptionGroup]):
    """Keep manifest rows that match a catalog/disk option group."""
    if not groups:
        skipped = [f"{e.underlying}/{e.expiry_kind}/{e.expiry_code}" for e in entries]
        logger.info(
            "catalog_gate: no option groups in catalog — skipping %d manifest groups",
            len(skipped),
        )
        return [], skipped
    allowed = {(g.underlying, g.expiry_kind, g.expiry_code) for g in groups}
    eligible = []
    skipped: list[str] = []
    for entry in entries:
        key = (
            normalize_symbol_for_storage(entry.underlying),
            entry.expiry_kind.upper(),
            int(entry.expiry_code),
        )
        if key in allowed:
            eligible.append(entry)
        else:
            skipped.append(f"{entry.underlying}/{entry.expiry_kind}/{entry.expiry_code}")
    if skipped:
        logger.info(
            "catalog_gate: skipped %d option groups not in catalog",
            len(skipped),
        )
    return eligible, skipped


def gate_contract_sync_entries(entries, groups: list[CatalogOptionGroup]):
    """Contract sync only for rolling groups registered in catalog (or exact rows with symbol in catalog)."""
    if not groups and not entries:
        return [], []
    catalog_syms = {g.underlying for g in groups} if groups else frozenset()
    if not catalog_syms:
        catalog_syms = frozenset(list_catalog_symbols())
    allowed_rolling = (
        {(g.underlying, g.expiry_kind, g.expiry_code) for g in groups} if groups else set()
    )
    eligible = []
    skipped: list[str] = []
    for entry in entries:
        underlying = entry.instrument_id.split(":")[1] if ":" in entry.instrument_id else ""
        underlying = normalize_symbol_for_storage(underlying)
        if entry.rolling_expiry_kind and entry.rolling_expiry_code is not None:
            key = (
                underlying,
                entry.rolling_expiry_kind.upper(),
                int(entry.rolling_expiry_code),
            )
            if allowed_rolling and key in allowed_rolling:
                eligible.append(entry)
            else:
                skipped.append(entry.instrument_id)
        elif underlying in catalog_syms:
            eligible.append(entry)
        else:
            skipped.append(entry.instrument_id)
    if skipped:
        logger.info(
            "catalog_gate: skipped %d contract entries not in catalog",
            len(skipped),
        )
    return eligible, skipped


def contract_entries_from_catalog(lake_root: str | None = None) -> list:
    """Return exact-contract manifest rows — never synthesized from rolling option groups."""
    return []
