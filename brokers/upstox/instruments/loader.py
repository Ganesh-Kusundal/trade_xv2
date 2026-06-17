"""Instrument catalog loader.

Mirrors Trade_J ``UpstoxInstrumentLoader``: streams the gz-compressed JSON
complete.json.gz from Upstox's CDN without loading the whole ~20MB file into
memory.

Cache Strategy:
- Raw cache: .cache/upstox/complete.json.gz (downloaded from Upstox)
- Parsed cache: .cache/upstox/instruments.json.gz (parsed Python objects as JSON)
- Only downloads if raw cache is older than 24h
- Only parses if parsed cache is newer than raw cache
- Migration: Old .pkl files are auto-migrated to .json.gz on first load
"""

from __future__ import annotations

import gzip
import json
import logging
import time
from collections.abc import Iterator
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from .definition import UpstoxInstrumentDefinition

logger = logging.getLogger(__name__)

COMPLETE_JSON_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
IST = ZoneInfo("Asia/Kolkata")
CACHE_VALIDITY_HOURS = 24  # Cache valid for 24 hours


class UpstoxInstrumentLoader:
    """Loads instrument definitions from Upstox's complete.json.gz (or a local file)."""

    def __init__(self, *, timeout_seconds: int = 60) -> None:
        self._timeout = timeout_seconds

    def download(self, cache_path: Path) -> Path:
        """Download instruments only if cache is missing or older than 1 day."""
        cache_path = Path(cache_path)

        # Check if cache is still valid
        if self._is_cache_valid(cache_path):
            logger.debug("Using cached instruments (valid for 24h)")
            return cache_path

        # Cache invalid or missing - download fresh
        logger.info("Downloading fresh instrument catalog from Upstox...")
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        start = time.time()
        with requests.get(COMPLETE_JSON_URL, stream=True, timeout=self._timeout) as resp:
            resp.raise_for_status()
            with open(cache_path, "wb") as fp:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        fp.write(chunk)

        elapsed = time.time() - start
        file_size_mb = cache_path.stat().st_size / (1024 * 1024)
        logger.info(
            f"Instrument catalog downloaded: {file_size_mb:.1f}MB in {elapsed:.1f}s"
        )
        return cache_path

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cache file exists and is less than 24 hours old."""
        if not cache_path.exists():
            return False

        try:
            file_age_seconds = time.time() - cache_path.stat().st_mtime
            file_age_hours = file_age_seconds / 3600

            if file_age_hours < CACHE_VALIDITY_HOURS:
                logger.debug(
                    f"Cache valid: {file_age_hours:.1f}h old (< {CACHE_VALIDITY_HOURS}h)"
                )
                return True
            else:
                logger.info(
                    f"Cache expired: {file_age_hours:.1f}h old (>= {CACHE_VALIDITY_HOURS}h)"
                )
                return False
        except Exception as e:
            logger.warning(f"Cache validation failed: {e}")
            return False

    def load(self, path: Path) -> list[UpstoxInstrumentDefinition]:
        """Load instruments with JSON+gzip caching for fast subsequent loads."""
        path = Path(path)
        json_gz_path = path.with_name(path.stem + '.parsed.json.gz')
        pkl_path = path.with_suffix('.pkl')

        # Migration: If old .pkl cache exists, migrate to .json.gz
        if pkl_path.exists() and not json_gz_path.exists():
            self._migrate_pickle_to_json(pkl_path, json_gz_path)

        # Try to load from JSON+gzip cache first
        if self._is_json_cache_valid(path, json_gz_path):
            try:
                start = time.time()
                defs = self._load_json_cache(json_gz_path)
                elapsed = time.time() - start
                logger.info(
                    f"Loaded {len(defs)} instruments from JSON cache in {elapsed:.2f}s"
                )
                return defs
            except Exception as e:
                logger.warning(f"JSON cache load failed: {e}")

        # Parse from JSON/gz (slow)
        logger.info("Parsing instrument catalog from JSON...")
        start = time.time()
        defs = []
        for d in self.iter_definitions(path):
            defs.append(d)
        elapsed = time.time() - start

        # Save to JSON+gzip cache
        try:
            self._save_json_cache(defs, json_gz_path)
            cache_size_mb = json_gz_path.stat().st_size / (1024*1024)
            logger.info(
                f"Parsed {len(defs)} instruments in {elapsed:.2f}s "
                f"(JSON cache: {cache_size_mb:.1f}MB)"
            )
        except Exception as e:
            logger.warning(f"Failed to save JSON cache: {e}")

        return defs

    def _migrate_pickle_to_json(self, pkl_path: Path, json_gz_path: Path) -> None:
        """Migrate old pickle cache to safe JSON+gzip format."""
        try:
            logger.info("Migrating pickle cache to JSON+gzip format...")
            import pickle
            with open(pkl_path, 'rb') as f:
                defs = pickle.load(f)
            self._save_json_cache(defs, json_gz_path)
            # Remove old pickle file after successful migration
            pkl_path.unlink()
            logger.info(f"Migration complete: {pkl_path.name} → {json_gz_path.name}")
        except Exception as e:
            logger.warning(f"Pickle migration failed: {e}")
            # Don't fail - will rebuild from JSON source

    def _load_json_cache(self, json_gz_path: Path) -> list[UpstoxInstrumentDefinition]:
        """Load instrument definitions from JSON+gzip cache."""
        with gzip.open(json_gz_path, 'rt', encoding='utf-8') as f:
            data = json.load(f)
        return [UpstoxInstrumentDefinition(**item) for item in data]

    def _save_json_cache(self, defs: list[UpstoxInstrumentDefinition], json_gz_path: Path) -> None:
        """Save instrument definitions to JSON+gzip cache."""
        # Convert dataclasses to dicts
        data = [d.to_dict() if hasattr(d, 'to_dict') else d.__dict__ for d in defs]
        with gzip.open(json_gz_path, 'wt', encoding='utf-8') as f:
            json.dump(data, f, separators=(',', ':'))  # Compact format

    def _is_json_cache_valid(self, json_path: Path, json_gz_path: Path) -> bool:
        """Check if JSON cache exists and is newer than source JSON."""
        if not json_gz_path.exists():
            return False
        if not json_path.exists():
            return False

        try:
            cache_mtime = json_gz_path.stat().st_mtime
            source_mtime = json_path.stat().st_mtime
            return cache_mtime >= source_mtime
        except Exception:
            return False

    def iter_definitions(self, path: Path) -> Iterator[UpstoxInstrumentDefinition]:
        path = Path(path)
        if path.suffix == ".gz":

            def opener():
                return gzip.open(path, "rt", encoding="utf-8")
        else:

            def opener():
                return open(path, encoding="utf-8")

        with opener() as fp:
            try:
                data = json.load(fp)
            except json.JSONDecodeError:
                logger.exception("Failed to parse instrument file %s", path)
                return
        if not isinstance(data, list):
            return
        for record in data:
            if not isinstance(record, dict):
                continue
            try:
                yield self._build_definition(record)
            except Exception:
                logger.debug("Skipping malformed record", exc_info=True)
                continue

    def _build_definition(self, record: dict) -> UpstoxInstrumentDefinition:
        from .segment_mapper import UpstoxSegmentMapper

        instrument_key = record.get("instrument_key") or ""
        segment = record.get("segment") or record.get("exchange_segment") or ""
        if not instrument_key or not segment:
            raise ValueError("Missing instrument_key or segment")
        known_segments = set(UpstoxSegmentMapper.all_upstox_segments())
        if segment.upper() not in known_segments:
            raise ValueError(f"Unknown segment: {segment}")

        expiry_val = record.get("expiry")
        if isinstance(expiry_val, int | float):
            from datetime import datetime, timezone
            try:
                expiry_val = datetime.fromtimestamp(expiry_val / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            except Exception:
                expiry_val = None

        return UpstoxInstrumentDefinition(
            instrument_key=instrument_key,
            exchange=record.get("exchange", "") or "",
            exchange_segment=segment,
            instrument_type=record.get("instrument_type", "") or "",
            symbol=record.get("symbol", "") or "",
            trading_symbol=record.get("trading_symbol", "") or record.get("symbol", "") or "",
            name=record.get("name", "") or "",
            isin=record.get("isin", "") or "",
            lot_size=int(record.get("lot_size", 0) or 0),
            tick_size=float(record.get("tick_size", 0) or 0.0),
            expiry=expiry_val,
            strike=_to_float(record.get("strike")),
            option_type=record.get("option_type") or record.get("instrument_type") or None,
            underlying_key=record.get("underlying_key") or record.get("underlying_symbol") or None,
            underlying_symbol=record.get("underlying_symbol") or None,
            freeze_qty=_to_int(record.get("freeze_qty")),
            minimum_lot=_to_int(record.get("minimum_lot")),
            short_name=record.get("short_name") or None,
            company_name=record.get("company_name") or None,
        )


def _to_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
