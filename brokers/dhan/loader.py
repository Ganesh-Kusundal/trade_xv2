"""Instrument master CSV loader with daily cache + MCX detailed supplement."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from brokers.dhan.segments import _COMPACT_SEGMENT_MAP

logger = logging.getLogger(__name__)

_COMPACT_CSV_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
_DETAILED_MCX_URL = "https://api.dhan.co/v2/instrument/MCX_COMM"
_CACHE_DIR = Path("runtime-dev/instruments")


class InstrumentLoader:
    """Downloads and parses Dhan instrument master with daily caching."""

    @staticmethod
    def load_cached(force_refresh: bool = False) -> list[dict]:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        cache_path = _CACHE_DIR / f"instruments_{today}.csv"

        if not force_refresh and cache_path.exists() and cache_path.stat().st_size > 0:
            logger.info("Loading instruments from cache: %s", cache_path)
            df = pd.read_csv(cache_path, low_memory=False)
            rows = InstrumentLoader._compact_to_rows(df)
        else:
            logger.info("Downloading instruments from Dhan...")
            df = pd.read_csv(_COMPACT_CSV_URL, low_memory=False)
            df.to_csv(cache_path, index=False)
            rows = InstrumentLoader._compact_to_rows(df)

        # Supplement with MCX detailed API (has GOLD/CRUDEOIL futures missing from compact)
        try:
            mcx_rows = InstrumentLoader._fetch_mcx_detailed()
            # Deduplicate: detailed API overrides compact CSV for same security_id
            existing_sids = {r["SEM_SMST_SECURITY_ID"] for r in rows}
            new_mcx = [r for r in mcx_rows if r["SEM_SMST_SECURITY_ID"] not in existing_sids]
            rows.extend(new_mcx)
            logger.info("Merged %d new MCX instruments (%d duplicates skipped)", len(new_mcx), len(mcx_rows) - len(new_mcx))
        except Exception as exc:
            logger.warning("MCX detailed fetch failed (non-fatal): %s", exc)

        return rows

    @staticmethod
    def load_from_file(path: str | Path) -> list[dict]:
        df = pd.read_csv(path, low_memory=False)
        return InstrumentLoader._compact_to_rows(df)

    @staticmethod
    def load_from_url(url: str) -> list[dict]:
        df = pd.read_csv(url, low_memory=False)
        return InstrumentLoader._compact_to_rows(df)

    @staticmethod
    def _compact_to_rows(df) -> list[dict]:
        out: list[dict] = []
        for r in df.itertuples(index=False):
            exch_id = str(getattr(r, "SEM_EXM_EXCH_ID", ""))
            segment = str(getattr(r, "SEM_SEGMENT", ""))
            seg = _COMPACT_SEGMENT_MAP.get((exch_id, segment))
            if seg is None:
                continue
            out.append({
                "SEM_TRADING_SYMBOL": str(getattr(r, "SEM_TRADING_SYMBOL", "")),
                "SEM_SMST_SECURITY_ID": str(int(getattr(r, "SEM_SMST_SECURITY_ID", 0))),
                "SEM_EXM_EXCH_ID": seg,
                "SEM_INSTRUMENT_NAME": str(getattr(r, "SEM_INSTRUMENT_NAME", "")),
                "SEM_LOT_UNITS": _safe_float(r, "SEM_LOT_UNITS", 1),
                "SEM_TICK_SIZE": _safe_float(r, "SEM_TICK_SIZE", 0.05),
                "SEM_EXPIRY_DATE": _safe_str(r, "SEM_EXPIRY_DATE"),
                "SEM_STRIKE_PRICE": _safe_opt_float(r, "SEM_STRIKE_PRICE"),
                "SEM_OPTION_TYPE": _safe_opt_str(r, "SEM_OPTION_TYPE"),
                "SEM_CUSTOM_SYMBOL": _safe_opt_str(r, "SEM_CUSTOM_SYMBOL"),
            })
        return out

    @staticmethod
    def _fetch_mcx_detailed() -> list[dict]:
        """Fetch MCX instruments from Dhan's detailed segment API.

        The compact CSV is missing many MCX futures (GOLD, CRUDEOIL, etc.).
        The detailed API at /v2/instrument/MCX_COMM has them with
        UNDERLYING_SECURITY_ID needed for option chain calls.
        """
        import csv
        import io
        import urllib.request

        req = urllib.request.Request(
            _DETAILED_MCX_URL,
            headers={"User-Agent": "TradeXV2/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8")

        reader = csv.DictReader(io.StringIO(content))
        rows: list[dict] = []
        for r in reader:
            if r.get("SEGMENT") != "M":
                continue
            rows.append({
                "SEM_TRADING_SYMBOL": (r.get("SYMBOL_NAME") or "").strip(),
                "SEM_SMST_SECURITY_ID": (r.get("SECURITY_ID") or "").strip(),
                "SEM_EXM_EXCH_ID": "MCX_COMM",
                "SEM_INSTRUMENT_NAME": (r.get("INSTRUMENT") or "").strip(),
                "SEM_LOT_UNITS": _safe_float_dict(r, "LOT_SIZE", 1),
                "SEM_TICK_SIZE": _safe_float_dict(r, "TICK_SIZE", 0.05),
                "SEM_EXPIRY_DATE": (r.get("SM_EXPIRY_DATE") or "").strip() or None,
                "SEM_STRIKE_PRICE": (r.get("STRIKE_PRICE") or "").strip() or None,
                "SEM_OPTION_TYPE": (r.get("OPTION_TYPE") or "").strip() or None,
                "SEM_CUSTOM_SYMBOL": None,
            })
        return rows


def _safe_float(r, col: str, default):
    val = getattr(r, col, None)
    return val if pd.notna(val) else default


def _safe_str(r, col: str):
    val = getattr(r, col, None)
    return str(val) if pd.notna(val) else None


def _safe_opt_float(r, col: str):
    val = getattr(r, col, None)
    return val if pd.notna(val) else None


def _safe_opt_str(r, col: str):
    val = getattr(r, col, None)
    return str(val) if pd.notna(val) else None


def _safe_float_dict(r: dict, col: str, default):
    try:
        val = r.get(col, "")
        if val is None or val == "":
            return default
        return float(val)
    except (TypeError, ValueError):
        return default
