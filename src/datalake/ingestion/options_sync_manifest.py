"""Authoritative allowlist for options datalake daily sync."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

from datalake.core.symbols import normalize_symbol_for_storage

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "options_sync_manifest.csv"
DEFAULT_BOOTSTRAP_ROWS: tuple[tuple[str, str, int], ...] = (
    ("NIFTY", "WEEK", 1),
    ("NIFTY", "WEEK", 2),
    ("NIFTY", "MONTH", 1),
    ("BANKNIFTY", "WEEK", 1),
    ("BANKNIFTY", "WEEK", 2),
    ("BANKNIFTY", "MONTH", 1),
)


@dataclass(frozen=True)
class OptionsSyncManifestEntry:
    underlying: str
    expiry_kind: str
    expiry_code: int


def manifest_path(root: str) -> Path:
    return Path(root) / MANIFEST_FILENAME


def load_options_sync_manifest(root: str) -> list[OptionsSyncManifestEntry]:
    path = manifest_path(root)
    if not path.exists():
        raise FileNotFoundError(
            f"options sync manifest not found: {path}. "
            "Run bootstrap_options_sync_manifest() or sync with --bootstrap-manifest."
        )
    entries: list[OptionsSyncManifestEntry] = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or "underlying" not in reader.fieldnames:
            raise ValueError(f"{path}: expected header underlying,expiry_kind,expiry_code")
        for row in reader:
            u = normalize_symbol_for_storage((row.get("underlying") or "").strip())
            ek = (row.get("expiry_kind") or "").strip().upper()
            ec_raw = (row.get("expiry_code") or "").strip()
            if not u or not ek or not ec_raw:
                continue
            entries.append(
                OptionsSyncManifestEntry(underlying=u, expiry_kind=ek, expiry_code=int(ec_raw))
            )
    return entries


def write_options_sync_manifest(root: str, entries: list[OptionsSyncManifestEntry]) -> None:
    path = manifest_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    deduped = sorted({(e.underlying, e.expiry_kind, e.expiry_code) for e in entries})
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["underlying", "expiry_kind", "expiry_code"])
        writer.writerows(deduped)
    logger.info("Wrote options sync manifest: %s (%d groups)", path, len(deduped))


def bootstrap_options_sync_manifest(root: str, *, overwrite: bool = False) -> int:
    path = manifest_path(root)
    if path.exists() and not overwrite:
        return len(load_options_sync_manifest(root))
    entries = [
        OptionsSyncManifestEntry(u, ek, ec) for u, ek, ec in DEFAULT_BOOTSTRAP_ROWS
    ]
    write_options_sync_manifest(root, entries)
    return len(entries)
