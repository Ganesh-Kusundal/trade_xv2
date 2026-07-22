"""Authoritative allowlist for datalake daily sync.

``sync_all`` reads ``{lake_root}/sync_manifest.csv`` — it does **not** discover
symbols from the filesystem. New lake membership requires an explicit entry here
(via :func:`add_symbol_to_manifest`, :func:`bootstrap_sync_manifest_from_disk`,
or :func:`download_universe` which registers symbols before fetch).

Format::

    symbol,asset
    RELIANCE,equities
    NIFTY,indices
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from datalake.core.symbols import normalize_symbol_for_storage

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "sync_manifest.csv"
AssetKind = Literal["equities", "indices"]
VALID_ASSETS: frozenset[str] = frozenset({"equities", "indices"})
# Orphan indices from an old bulk download — excluded from bootstrap by default.
DEFAULT_BOOTSTRAP_EXCLUDE: frozenset[str] = frozenset({"BSE100", "BSE200", "BSE500"})


@dataclass(frozen=True)
class SyncManifestEntry:
    symbol: str
    asset: AssetKind


def manifest_path(root: str) -> Path:
    return Path(root) / MANIFEST_FILENAME


def load_sync_manifest(root: str) -> list[SyncManifestEntry]:
    """Load manifest entries. Raises ``FileNotFoundError`` if missing."""
    path = manifest_path(root)
    if not path.exists():
        raise FileNotFoundError(
            f"sync manifest not found: {path}. "
            "Run: python scripts/bootstrap_sync_manifest.py"
        )
    entries: list[SyncManifestEntry] = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or "symbol" not in reader.fieldnames:
            raise ValueError(f"{path}: expected header symbol,asset")
        for row in reader:
            sym = normalize_symbol_for_storage((row.get("symbol") or "").strip())
            asset = (row.get("asset") or "equities").strip().lower()
            if not sym:
                continue
            if asset not in VALID_ASSETS:
                raise ValueError(f"{path}: invalid asset {asset!r} for {sym}")
            entries.append(SyncManifestEntry(symbol=sym, asset=asset))  # type: ignore[arg-type]
    return entries


def write_sync_manifest(root: str, entries: list[SyncManifestEntry]) -> None:
    path = manifest_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    deduped = sorted({(e.symbol, e.asset) for e in entries})
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "asset"])
        writer.writerows(deduped)
    logger.info("Wrote sync manifest: %s (%d symbols)", path, len(deduped))


def add_symbol_to_manifest(root: str, symbol: str, asset: AssetKind) -> bool:
    """Append *symbol* if not already listed. Returns True when added."""
    symbol = normalize_symbol_for_storage(symbol)
    if asset not in VALID_ASSETS:
        raise ValueError(f"asset must be equities or indices, got {asset!r}")
    existing = {(e.symbol, e.asset) for e in _load_or_empty(root)}
    if (symbol, asset) in existing:
        return False
    existing.add((symbol, asset))
    write_sync_manifest(
        root,
        [SyncManifestEntry(sym, ast) for sym, ast in sorted(existing)],  # type: ignore[arg-type]
    )
    return True


def remove_symbol_from_manifest(root: str, symbol: str, asset: AssetKind) -> bool:
    symbol = normalize_symbol_for_storage(symbol)
    kept = [e for e in _load_or_empty(root) if not (e.symbol == symbol and e.asset == asset)]
    if len(kept) == len(_load_or_empty(root)):
        return False
    write_sync_manifest(root, kept)
    return True


def resolve_sync_work(
    root: str,
    *,
    assets: tuple[str, ...] = ("equities", "indices"),
    delisted: set[str] | None = None,
) -> list[SyncManifestEntry]:
    """Manifest entries eligible for this sync run."""
    delisted = delisted or set()
    asset_set = set(assets)
    work: list[SyncManifestEntry] = []
    for entry in load_sync_manifest(root):
        if entry.asset not in asset_set:
            continue
        if entry.symbol in delisted:
            continue
        work.append(entry)
    return work


def bootstrap_sync_manifest_from_disk(
    root: str,
    *,
    exclude: frozenset[str] | None = None,
    overwrite: bool = False,
) -> int:
    """Build ``sync_manifest.csv`` from on-disk hive dirs (one-time migration).

    Uses :func:`existing_symbols` per asset segment. Symbols in *exclude* are
    omitted (default: BSE100/200/500 orphans).
    """
    from datalake.ingestion.auto_sync import existing_symbols

    path = manifest_path(root)
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists; pass overwrite=True to replace")

    exclude = exclude if exclude is not None else DEFAULT_BOOTSTRAP_EXCLUDE
    entries: list[SyncManifestEntry] = []
    for asset in ("equities", "indices"):
        for sym in existing_symbols(root, asset, "1m"):
            if sym in exclude:
                logger.info("bootstrap: skipping excluded symbol %s", sym)
                continue
            entries.append(SyncManifestEntry(symbol=sym, asset=asset))  # type: ignore[arg-type]
    write_sync_manifest(root, entries)
    return len(entries)


def _load_or_empty(root: str) -> list[SyncManifestEntry]:
    try:
        return load_sync_manifest(root)
    except FileNotFoundError:
        return []
