"""Upstox instruments adapter — gzipped JSON master with file cache."""

from __future__ import annotations

import gzip
import io
import json
import logging
import os
import time
import urllib.request
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from domain.entities import Instrument
from domain.enums import AssetClass, ExchangeId, InstrumentType, OptionType
from domain.value_objects import InstrumentId
from plugins.brokers.upstox.instrument_adapter import to_instrument_id
from plugins.brokers.upstox.wire import UpstoxWire

if TYPE_CHECKING:
    from plugins.brokers.common.transport import BaseTransport

logger = logging.getLogger(__name__)

_UPSTOX_INSTRUMENT_JSON_GZ = (
    "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
)

_RUNTIME_DIR = Path(__file__).resolve().parents[4] / "runtime"

_INSTRUMENT_CACHE_TTL_HOURS = 6.0
_INSTRUMENT_CACHE_CLEANUP_DAYS = 7

# Real Upstox complete.json.gz has tens of thousands of instruments. A parsed
# result below this floor is a corrupt/truncated download — never trust it.
MIN_UPSTOX_INSTRUMENTS = 10_000

_SEG_EXCH: dict[str, ExchangeId] = {
    "NSE_EQ": ExchangeId.NSE,
    "NSE_FO": ExchangeId.NFO,
    "BSE_EQ": ExchangeId.BSE,
    "BSE_FO": ExchangeId.BFO,
    "MCX_FUT": ExchangeId.MCX,
    "MCX_FO": ExchangeId.MCX,
    "NCD_FO": ExchangeId.CDS,
    "NSE_INDEX": ExchangeId.NSE,
    "BSE_INDEX": ExchangeId.BSE,
}

_SEG_ASSET: dict[str, AssetClass] = {
    "NSE_EQ": AssetClass.EQUITY,
    "BSE_EQ": AssetClass.EQUITY,
    "NSE_FO": AssetClass.DERIVATIVE,
    "BSE_FO": AssetClass.DERIVATIVE,
    "MCX_FO": AssetClass.COMMODITY,
    "MCX_FUT": AssetClass.COMMODITY,
    "NCD_FO": AssetClass.CURRENCY,
    "NSE_INDEX": AssetClass.INDEX,
    "BSE_INDEX": AssetClass.INDEX,
}

_SEG_ITYPE: dict[str, InstrumentType] = {
    "NSE_EQ": InstrumentType.EQUITY,
    "BSE_EQ": InstrumentType.EQUITY,
    "NSE_FO": InstrumentType.OPTION,
    "BSE_FO": InstrumentType.OPTION,
    "MCX_FUT": InstrumentType.FUTURE,
    "NCD_FO": InstrumentType.FUTURE,
    "NSE_INDEX": InstrumentType.INDEX,
    "BSE_INDEX": InstrumentType.INDEX,
}


class UpstoxInstrumentAdapter:
    def __init__(self, transport: BaseTransport, wire: UpstoxWire | None = None) -> None:
        self._transport = transport
        self._wire = wire or UpstoxWire()
        self._by_id: dict[str, Instrument] = {}

    def load_instruments(self) -> list[Instrument]:
        try:
            return self._load_with_cache()
        except Exception as exc:
            logger.error("Upstox instrument load failed: %s", exc)
            raise

    def _load_with_cache(self) -> list[Instrument]:
        cache_dir = _RUNTIME_DIR
        cache_dir.mkdir(parents=True, exist_ok=True)

        today = date.today().isoformat()
        cache_path = cache_dir / f"upstox-instruments-{today}.json.gz"

        self._cleanup_old_cache(cache_dir)

        # Check cache freshness
        force_refresh = False
        if cache_path.exists() and cache_path.stat().st_size > 0:
            try:
                mtime = datetime.fromtimestamp(cache_path.stat().st_mtime, tz=timezone.utc)
                cache_age_hours = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600.0
                if cache_age_hours > _INSTRUMENT_CACHE_TTL_HOURS:
                    logger.info("Cache age %.1fh > %.1fh, refreshing", cache_age_hours, _INSTRUMENT_CACHE_TTL_HOURS)
                    force_refresh = True
            except Exception:
                force_refresh = True

        rows: list[dict] | None = None
        if not force_refresh and cache_path.exists() and cache_path.stat().st_size > 0:
            logger.info("Loading Upstox instruments from cache: %s", cache_path)
            try:
                candidate = self._decode_json_gz(cache_path.read_bytes())
                if len(candidate) >= MIN_UPSTOX_INSTRUMENTS:
                    rows = candidate
                else:
                    logger.warning(
                        "Cached instrument file %s has too few rows (%d < %d) — discarding, re-downloading",
                        cache_path,
                        len(candidate),
                        MIN_UPSTOX_INSTRUMENTS,
                    )
            except Exception as exc:
                logger.warning("Failed to read cache: %s", exc)

        if rows is None:
            raw_bytes = self._download_json_gz(_UPSTOX_INSTRUMENT_JSON_GZ)
            rows = self._decode_json_gz(raw_bytes)
            if len(rows) < MIN_UPSTOX_INSTRUMENTS:
                raise ValueError(
                    f"Upstox instrument master download has too few rows "
                    f"({len(rows)} < {MIN_UPSTOX_INSTRUMENTS}) — refusing to accept as valid instrument master"
                )
            tmp_path = cache_path.with_suffix(".json.gz.tmp")
            tmp_path.write_bytes(raw_bytes)
            os.replace(tmp_path, cache_path)

        return self._rows_to_instruments(rows)

    def _download_json_gz(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "TradeXV2/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()

    def _decode_json_gz(self, raw_bytes: bytes) -> list[dict]:
        try:
            text = gzip.decompress(raw_bytes).decode("utf-8")
        except Exception:
            # Fallback: maybe it's plain JSON (not gzipped)
            text = raw_bytes.decode("utf-8")
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError(f"Expected JSON array, got {type(data).__name__}")
        return data

    def _rows_to_instruments(self, rows: list[dict]) -> list[Instrument]:
        """Build the by-id map and wire registrations off to the side, then
        commit both in one step — a concurrent reader never sees a partially
        parsed master mid-refresh. Duplicate canonical ids are logged."""
        out: list[Instrument] = []
        new_by_id: dict[str, Instrument] = {}
        wire_rows: list[dict] = []
        duplicates = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            inst = self._to_instrument(row)
            if inst is None:
                continue
            if inst.instrument_id.value in new_by_id:
                duplicates += 1
            new_by_id[inst.instrument_id.value] = inst
            key = str(row.get("instrument_key") or "")
            if key:
                wire_rows.append({"instrument_id": inst.instrument_id, "wire": {"instrument_key": key}})
            out.append(inst)
        self._by_id = new_by_id
        self._wire.register_bulk(wire_rows, source="upstox_json")
        if duplicates:
            logger.warning(
                "upstox_instrument_duplicates: %d duplicate canonical ids in JSON parse (last-write-wins)",
                duplicates,
            )
        logger.info("Upstox instruments loaded: %d", len(out))
        return out

    def search(self, query: str) -> list[Instrument]:
        q = query.upper()
        return [i for i in self._by_id.values() if q in i.symbol.upper()]

    def _to_instrument(self, row: dict[str, Any]) -> Instrument | None:
        instrument_key = str(row.get("instrument_key") or "")
        segment = str(row.get("segment") or row.get("exchange_segment") or "").upper()
        if not segment:
            return None

        symbol = str(row.get("symbol") or row.get("trading_symbol") or instrument_key.split("|")[-1] or "").strip()
        if not symbol:
            return None

        exch = _SEG_EXCH.get(segment, ExchangeId.NSE)
        asset_class = _SEG_ASSET.get(segment, AssetClass.EQUITY)
        instrument_type = _SEG_ITYPE.get(segment, InstrumentType.EQUITY)

        # G10: Strip -EQ suffix from equity symbols to match src convention
        display_symbol = symbol
        if instrument_type == InstrumentType.EQUITY and symbol.endswith("-EQ"):
            display_symbol = symbol[:-3]

        option_type = None
        raw_opt = str(row.get("option_type") or "").upper().strip()
        if raw_opt in ("CE", "CALL", "C"):
            option_type = OptionType.CALL
        elif raw_opt in ("PE", "PUT", "P"):
            option_type = OptionType.PUT

        strike = None
        strike_raw = row.get("strike_price") or row.get("strike")
        if strike_raw not in (None, 0, "0", ""):
            try:
                strike = Decimal(str(strike_raw))
            except (ValueError, TypeError):
                pass

        # NSE_FO/BSE_FO cover both futures and options — the segment alone
        # can't distinguish them (_SEG_ITYPE defaults to OPTION). A row with
        # no strike/option_type in an F&O segment is a future, not an option.
        if instrument_type == InstrumentType.OPTION and (option_type is None or strike is None):
            instrument_type = InstrumentType.FUTURE

        expiry = None
        expiry_raw = row.get("expiry")
        if expiry_raw:
            try:
                if isinstance(expiry_raw, (int, float)):
                    expiry = datetime.fromtimestamp(expiry_raw / 1000, tz=timezone.utc).replace(tzinfo=None)
                else:
                    expiry = datetime.strptime(str(expiry_raw)[:10], "%Y-%m-%d")
            except (ValueError, TypeError, OSError):
                pass

        lot_size = None
        lot_raw = row.get("lot_size")
        if lot_raw not in (None, 0, "0", ""):
            try:
                lot_size = Decimal(str(lot_raw))
            except (ValueError, TypeError):
                pass

        tick_size = None
        tick_raw = row.get("tick_size")
        if tick_raw not in (None, 0, "0", ""):
            try:
                tick_size = Decimal(str(tick_raw))
            except (ValueError, TypeError):
                pass

        underlying = str(row.get("underlying_symbol") or row.get("asset_symbol") or "").strip() or None
        iid = to_instrument_id(
            symbol=display_symbol,
            exchange=exch.value,
            instrument_type=instrument_type,
            underlying=underlying,
            expiry=expiry.date() if expiry else None,
            strike=strike,
            option_type=option_type,
        )

        return Instrument(
            instrument_id=iid,
            symbol=display_symbol,
            exchange=exch,
            asset_class=asset_class,
            currency="INR",
            instrument_type=instrument_type,
            strike=strike,
            expiry=expiry,
            option_type=option_type,
            lot_size=lot_size,
            tick_size=tick_size,
        )

    def _cleanup_old_cache(self, cache_dir: Path) -> None:
        now = time.time()
        cutoff = now - (_INSTRUMENT_CACHE_CLEANUP_DAYS * 24 * 3600)
        try:
            for path in cache_dir.glob("upstox-instruments-*.json.gz"):
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("Cache cleanup failed: %s", exc)
