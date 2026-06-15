"""Instrument catalog loader.

Mirrors Trade_J ``UpstoxInstrumentLoader``: streams the gz-compressed JSON
complete.json.gz from Upstox's CDN without loading the whole ~20MB file into
memory.
"""

from __future__ import annotations

import gzip
import json
import logging
from collections.abc import Iterator
from pathlib import Path

import requests

from .definition import UpstoxInstrumentDefinition

logger = logging.getLogger(__name__)

COMPLETE_JSON_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"


class UpstoxInstrumentLoader:
    """Loads instrument definitions from Upstox's complete.json.gz (or a local file)."""

    def __init__(self, *, timeout_seconds: int = 60) -> None:
        self._timeout = timeout_seconds

    def download(self, cache_path: Path) -> Path:
        cache_path = Path(cache_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(COMPLETE_JSON_URL, stream=True, timeout=self._timeout) as resp:
            resp.raise_for_status()
            with open(cache_path, "wb") as fp:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        fp.write(chunk)
        return cache_path

    def load(self, path: Path) -> list[UpstoxInstrumentDefinition]:
        defs: list[UpstoxInstrumentDefinition] = []
        for d in self.iter_definitions(path):
            defs.append(d)
        return defs

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
        if isinstance(expiry_val, (int, float)):
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
