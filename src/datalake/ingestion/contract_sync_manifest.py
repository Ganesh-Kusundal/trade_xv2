"""Manifest for contract-centric historical sync (ADR-0023)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from domain.instruments.instrument_id import InstrumentId
from domain.ports.data_catalog import DEFAULT_DATA_PATHS

MANIFEST_FILENAME = "contract_sync_manifest.csv"
DEFAULT_BOOTSTRAP_ROWS: tuple[tuple[str, str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class ContractSyncManifestEntry:
    instrument_id: str
    timeframe: str
    asset_class: str  # option | future | equity
    rolling_expiry_kind: str | None = None  # WEEK | MONTH — Dhan rolling lane
    rolling_expiry_code: int | None = None
    rolling_strike_offset: int | None = None


MANIFEST_FIELDS = (
    "instrument_id",
    "timeframe",
    "asset_class",
    "rolling_expiry_kind",
    "rolling_expiry_code",
    "rolling_strike_offset",
)


def manifest_path(lake_root: str | None = None) -> Path:
    root = lake_root or DEFAULT_DATA_PATHS.lake_root
    return Path(root) / MANIFEST_FILENAME


def bootstrap_contract_sync_manifest(lake_root: str | None = None) -> Path:
    """Create empty contract manifest when missing.

    Exact-contract rows only — rolling index options stay on options_sync_manifest.
    """
    path = manifest_path(lake_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        entries = load_contract_sync_manifest(lake_root)
        if entries:
            return path
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(MANIFEST_FIELDS))
        writer.writeheader()
        for iid, tf, ac in DEFAULT_BOOTSTRAP_ROWS:
            writer.writerow(
                {
                    "instrument_id": iid,
                    "timeframe": tf,
                    "asset_class": ac,
                    "rolling_expiry_kind": "",
                    "rolling_expiry_code": "",
                    "rolling_strike_offset": "",
                }
            )
    return path


def write_contract_sync_manifest(
    lake_root: str | None, entries: list[ContractSyncManifestEntry]
) -> Path:
    path = manifest_path(lake_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    deduped: dict[tuple, ContractSyncManifestEntry] = {}
    for e in entries:
        key = (e.instrument_id, e.timeframe, e.asset_class, e.rolling_expiry_kind, e.rolling_expiry_code)
        deduped[key] = e
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(MANIFEST_FIELDS))
        writer.writeheader()
        for e in sorted(deduped.values(), key=lambda x: (x.instrument_id, x.timeframe)):
            writer.writerow(
                {
                    "instrument_id": e.instrument_id,
                    "timeframe": e.timeframe,
                    "asset_class": e.asset_class,
                    "rolling_expiry_kind": e.rolling_expiry_kind or "",
                    "rolling_expiry_code": (
                        e.rolling_expiry_code if e.rolling_expiry_code is not None else ""
                    ),
                    "rolling_strike_offset": (
                        e.rolling_strike_offset if e.rolling_strike_offset is not None else ""
                    ),
                }
            )
    return path


def bootstrap_contract_sync_manifest_from_options(lake_root: str | None = None) -> int:
    """No-op — rolling groups belong on options_sync_manifest, not contract manifest."""
    bootstrap_contract_sync_manifest(lake_root)
    return 0


def bootstrap_contract_sync_manifest_from_catalog(lake_root: str | None = None) -> int:
    """No-op — contract manifest is seeded only with exact instrument rows."""
    bootstrap_contract_sync_manifest(lake_root)
    return 0


def load_contract_sync_manifest(lake_root: str | None = None) -> list[ContractSyncManifestEntry]:
    path = manifest_path(lake_root)
    if not path.exists():
        bootstrap_contract_sync_manifest(lake_root)
    entries: list[ContractSyncManifestEntry] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rek = (row.get("rolling_expiry_kind") or "").strip().upper() or None
            rec_raw = (row.get("rolling_expiry_code") or "").strip()
            rso_raw = (row.get("rolling_strike_offset") or "").strip()
            entries.append(
                ContractSyncManifestEntry(
                    instrument_id=row["instrument_id"].strip(),
                    timeframe=row["timeframe"].strip(),
                    asset_class=row["asset_class"].strip().lower(),
                    rolling_expiry_kind=rek,
                    rolling_expiry_code=int(rec_raw) if rec_raw else None,
                    rolling_strike_offset=int(rso_raw) if rso_raw else None,
                )
            )
    return entries


def parse_manifest_instrument(entry: ContractSyncManifestEntry) -> InstrumentId:
    """Parse manifest instrument_id; partial ids get minimal fields."""
    text = entry.instrument_id.strip()
    if ":" not in text:
        raise ValueError(f"invalid instrument_id: {text!r}")
    parts = text.split(":")
    if len(parts) == 2:
        return InstrumentId.equity(parts[0], parts[1])
    return InstrumentId.parse(text)
