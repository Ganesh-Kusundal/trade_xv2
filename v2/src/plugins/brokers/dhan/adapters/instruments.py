"""Dhan instrument master loader + search with CSV caching."""

from __future__ import annotations

import csv
import io
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
from plugins.brokers.dhan.instrument_adapter import to_instrument_id
from plugins.brokers.dhan.wire import DhanWire

if TYPE_CHECKING:
    from plugins.brokers.common.transport import BaseTransport

logger = logging.getLogger(__name__)

DHAN_INSTRUMENT_CSV = "https://images.dhan.co/api-data/api-scrip-master.csv"
DHAN_MCX_COMM_URL = "https://api.dhan.co/v2/instrument/MCX_COMM"

_RUNTIME_DIR = Path(__file__).resolve().parents[4] / "runtime"

# Real Dhan compact CSV has ~220k rows. A file below this floor is a corrupt
# download or a stray test fixture — never trust it as the instrument master.
MIN_DHAN_INSTRUMENTS = 10_000

_INSTRUMENT_CACHE_TTL_HOURS = 6.0
_INSTRUMENT_CACHE_CLEANUP_DAYS = 7

_SEGMENT_MAP: dict[tuple[str, str], ExchangeId] = {
    ("NSE", "E"): ExchangeId.NSE,
    ("NSE", "D"): ExchangeId.NFO,
    ("NSE", "I"): ExchangeId.IDX,
    ("BSE", "E"): ExchangeId.BSE,
    ("BSE", "D"): ExchangeId.BFO,
    ("BSE", "I"): ExchangeId.IDX,
    ("MCX", "M"): ExchangeId.MCX,
    ("CDS", "D"): ExchangeId.CDS,
    ("NSE", "C"): ExchangeId.CDS,
    ("BSE", "C"): ExchangeId.BCD,
    # Dhan dual-lists some MCX commodity contracts under NSE with a distinct
    # security_id — kept as its own exchange (not collapsed to MCX) so the
    # two real listings never collide on the same canonical InstrumentId.
    ("NSE", "M"): ExchangeId.NSE_COMM,
}

# Real Dhan scrip-master SEM_INSTRUMENT_NAME vocabulary (verified against the
# live CSV: OPTSTK 108k, OPTFUT 46k, OPTCUR 24k, EQUITY 23k, OPTIDX 17k,
# FUTSTK 1.3k, FUTCUR 290, INDEX 191, FUTCOM 144, FUTIDX 35).
_INSTRUMENT_TYPE_MAP: dict[str, InstrumentType] = {
    "EQUITY": InstrumentType.EQUITY,
    "FUTIDX": InstrumentType.FUTURE,
    "FUTSTK": InstrumentType.FUTURE,
    "FUTCOM": InstrumentType.FUTURE,
    "FUTCUR": InstrumentType.FUTURE,
    "OPTIDX": InstrumentType.OPTION,
    "OPTSTK": InstrumentType.OPTION,
    "OPTCOM": InstrumentType.OPTION,
    "OPTFUT": InstrumentType.OPTION,
    "OPTCUR": InstrumentType.OPTION,
    "INDEX": InstrumentType.INDEX,
    "BE": InstrumentType.EQUITY,
    "BOND": InstrumentType.EQUITY,
}

_OPTION_TYPE_MAP: dict[str, OptionType] = {
    "CE": OptionType.CALL,
    "PE": OptionType.PUT,
    "CA": OptionType.CALL,
    "PA": OptionType.PUT,
}


class DhanInstrumentAdapter:
    def __init__(self, transport: BaseTransport, wire: DhanWire | None = None) -> None:
        self._transport = transport
        self._wire = wire or DhanWire()
        self._by_id: dict[str, Instrument] = {}

    def load_instruments(self, *, force_refresh: bool = False) -> list[Instrument]:
        instruments = self.load_from_csv(force_refresh=force_refresh)
        # Register index instruments from the hardcoded index map
        self._register_indices()
        return instruments

    def _register_indices(self) -> None:
        """Register hardcoded index instruments (NIFTY, BANKNIFTY, etc.) on the wire.

        Canonical exchange is the index's real home listing (NSE/BSE), derived
        from ``upstox_segment`` — matches Upstox's own index InstrumentIds
        (``_SEG_EXCH`` maps NSE_INDEX/BSE_INDEX -> ExchangeId.NSE/BSE) so both
        brokers converge on the same id for the same index.
        """
        from plugins.brokers.common.index_map import _INDEX_MAP

        for symbol, entry in _INDEX_MAP.items():
            if entry.dhan_security_id is None:
                continue
            exchange = ExchangeId.BSE if entry.upstox_segment == "BSE_INDEX" else ExchangeId.NSE
            iid = to_instrument_id(symbol=symbol, exchange=exchange.value, instrument_type=InstrumentType.INDEX)
            self._wire.register_security(
                iid,
                entry.dhan_security_id,
                symbol=symbol,
                exchange=exchange.value,
                instrument_type="INDEX",
                canonical_symbol=entry.canonical_name,
            )
            if iid.value not in self._by_id:
                inst = Instrument(
                    instrument_id=iid,
                    symbol=symbol,
                    exchange=exchange,
                    asset_class=AssetClass.INDEX,
                    currency="INR",
                    instrument_type=InstrumentType.INDEX,
                )
                self._by_id[iid.value] = inst

    def load_from_csv(self, *, force_refresh: bool = False) -> list[Instrument]:
        cache_dir = _RUNTIME_DIR
        cache_dir.mkdir(parents=True, exist_ok=True)

        today = date.today().isoformat()
        cache_path = cache_dir / f"dhan-instruments-{today}.csv"

        self._cleanup_old_cache(cache_dir)

        # A caller-requested force (e.g. the daily scheduler) bypasses the
        # TTL gate entirely — re-download even when the cache is fresh.
        if force_refresh:
            force_redownload = True
        else:
            force_redownload = False
            if cache_path.exists() and cache_path.stat().st_size > 0:
                try:
                    mtime = datetime.fromtimestamp(cache_path.stat().st_mtime, tz=timezone.utc)
                    cache_age_hours = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600.0
                    if cache_age_hours > _INSTRUMENT_CACHE_TTL_HOURS:
                        logger.info("Cache age %.1fh > %.1fh, refreshing", cache_age_hours, _INSTRUMENT_CACHE_TTL_HOURS)
                        force_redownload = True
                except Exception:
                    force_redownload = True

        csv_content = None
        if not force_redownload and cache_path.exists() and cache_path.stat().st_size > 0:
            logger.info("Loading instruments from cache: %s", cache_path)
            try:
                candidate = cache_path.read_text(encoding="utf-8")
                if candidate.count("\n") >= MIN_DHAN_INSTRUMENTS:
                    csv_content = candidate
                else:
                    logger.warning(
                        "Cached instrument file %s has too few rows (< %d) — discarding, re-downloading",
                        cache_path,
                        MIN_DHAN_INSTRUMENTS,
                    )
            except Exception as exc:
                logger.warning("Failed to read cache: %s", exc)

        if csv_content is None:
            csv_content = self._download_csv(DHAN_INSTRUMENT_CSV)
            if csv_content.count("\n") < MIN_DHAN_INSTRUMENTS:
                raise ValueError(
                    f"Dhan instrument master download has too few rows (< {MIN_DHAN_INSTRUMENTS}) "
                    "— refusing to accept as valid instrument master"
                )
            tmp_path = cache_path.with_suffix(".csv.tmp")
            tmp_path.write_text(csv_content, encoding="utf-8")
            os.replace(tmp_path, cache_path)

        instruments = self._parse_csv_to_instruments(csv_content)

        mcx_instruments = self._fetch_mcx_supplement()
        if mcx_instruments:
            existing_ids = {i.instrument_id.value for i in instruments}
            added = 0
            for inst in mcx_instruments:
                if inst.instrument_id.value not in existing_ids:
                    instruments.append(inst)
                    self._by_id[inst.instrument_id.value] = inst
                    added += 1
            logger.info("MCX supplement: added %d instruments", added)

        return instruments

    def _download_csv(self, url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "TradeXV2/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")

    def _parse_csv_to_instruments(self, csv_content: str) -> list[Instrument]:
        """Build the by-id map and wire registrations off to the side, then
        commit both in one step — a concurrent reader never sees a partially
        parsed master mid-refresh. Duplicate canonical ids are logged."""
        reader = csv.DictReader(io.StringIO(csv_content))
        out: list[Instrument] = []
        new_by_id: dict[str, Instrument] = {}
        wire_rows: list[dict[str, Any]] = []
        duplicates = 0
        for row in reader:
            inst = self._csv_row_to_instrument(row)
            if inst is not None:
                if inst.instrument_id.value in new_by_id:
                    duplicates += 1
                new_by_id[inst.instrument_id.value] = inst
                sec = str(row.get("SEM_SMST_SECURITY_ID") or row.get("security_id") or "")
                if sec:
                    wire_rows.append({"instrument_id": inst.instrument_id, "wire": {"security_id": sec}})
                out.append(inst)
        self._by_id = new_by_id
        self._wire.register_bulk(wire_rows, source="dhan_csv")
        if duplicates:
            logger.warning(
                "dhan_instrument_duplicates: %d duplicate canonical ids in CSV parse (last-write-wins)",
                duplicates,
            )
        return out

    def _csv_row_to_instrument(self, row: dict[str, Any]) -> Instrument | None:
        symbol = (row.get("SEM_TRADING_SYMBOL") or row.get("trading_symbol") or "").strip()
        if not symbol:
            return None

        exch_id = (row.get("SEM_EXM_EXCH_ID") or row.get("exchange") or "NSE").strip().upper()
        segment = (row.get("SEM_SEGMENT") or row.get("segment") or "E").strip().upper()

        exchange = _SEGMENT_MAP.get((exch_id, segment))
        if exchange is None:
            exchange = ExchangeId.NSE if "NSE" in exch_id else ExchangeId.BSE if "BSE" in exch_id else ExchangeId.NSE

        inst_name = (row.get("SEM_INSTRUMENT_NAME") or row.get("instrument") or "").strip().upper()
        instrument_type = _INSTRUMENT_TYPE_MAP.get(inst_name, InstrumentType.EQUITY)

        asset_class = AssetClass.EQUITY
        if exchange in (ExchangeId.MCX, ExchangeId.NSE_COMM):
            asset_class = AssetClass.COMMODITY
        elif exchange in (ExchangeId.CDS, ExchangeId.BCD):
            asset_class = AssetClass.CURRENCY
        elif instrument_type in (InstrumentType.FUTURE, InstrumentType.OPTION):
            asset_class = AssetClass.DERIVATIVE

        lot_size = _safe_float(row.get("SEM_LOT_UNITS") or row.get("lot_size"), 1)
        tick_size = _safe_float(row.get("SEM_TICK_SIZE") or row.get("tick_size"), 0.05)
        expiry_str = (row.get("SEM_EXPIRY_DATE") or row.get("expiry_date") or "").strip() or None
        strike_str = (row.get("SEM_STRIKE_PRICE") or row.get("strike_price") or "").strip() or None
        option_type_str = (row.get("SEM_OPTION_TYPE") or row.get("option_type") or "").strip().upper()

        expiry = None
        if expiry_str:
            try:
                expiry = datetime.strptime(expiry_str.split()[0], "%Y-%m-%d")
            except (ValueError, TypeError):
                pass

        strike = None
        if strike_str:
            try:
                strike = Decimal(strike_str)
            except (ValueError, TypeError):
                pass
        # ponytail: futures/currency rows carry a -0.01 sentinel — never a real
        # strike, so drop it (matches the Upstox adapter's filter).
        if strike is not None and strike <= 0:
            strike = None

        option_type = _OPTION_TYPE_MAP.get(option_type_str) if option_type_str and option_type_str != "XX" else None

        # G10: Strip -EQ suffix from equity symbols to match src convention
        display_symbol = symbol
        if instrument_type == InstrumentType.EQUITY and symbol.endswith("-EQ"):
            display_symbol = symbol[:-3]

        underlying = (row.get("SM_SYMBOL_NAME") or "").strip() or None
        iid = to_instrument_id(
            symbol=display_symbol,
            exchange=exchange.value,
            instrument_type=instrument_type,
            underlying=underlying,
            expiry=expiry.date() if expiry else None,
            strike=strike,
            option_type=option_type,
        )
        return Instrument(
            instrument_id=iid,
            symbol=display_symbol,
            exchange=exchange,
            asset_class=asset_class,
            currency="INR",
            instrument_type=instrument_type,
            strike=strike,
            expiry=expiry,
            option_type=option_type,
            lot_size=Decimal(str(lot_size)),
            tick_size=Decimal(str(tick_size)),
        )

    def _fetch_mcx_supplement(self) -> list[Instrument]:
        try:
            csv_content = self._download_csv(DHAN_MCX_COMM_URL)
        except Exception as exc:
            logger.warning("MCX supplement fetch failed (non-fatal): %s", exc)
            return []

        reader = csv.DictReader(io.StringIO(csv_content))
        out: list[Instrument] = []
        for row in reader:
            segment = (row.get("SEGMENT") or "").strip().upper()
            if segment != "M":
                continue
            inst = self._mcx_row_to_instrument(row)
            if inst is not None:
                out.append(inst)
        return out

    def _mcx_row_to_instrument(self, row: dict[str, Any]) -> Instrument | None:
        symbol_name = (row.get("SYMBOL_NAME") or "").strip().upper()
        instrument = (row.get("INSTRUMENT") or "").strip().upper()
        expiry_str = (row.get("SM_EXPIRY_DATE") or "").strip()
        strike_str = (row.get("STRIKE_PRICE") or "").strip()
        option_type_str = (row.get("OPTION_TYPE") or "").strip().upper()
        security_id = (row.get("SECURITY_ID") or "").strip()

        trading_symbol = symbol_name
        if expiry_str:
            try:
                dt_str = expiry_str.split()[0]
                dt = datetime.strptime(dt_str, "%Y-%m-%d")
                dd_mmm_yyyy = dt.strftime("%d%b%Y")
                if "FUT" in instrument and "OPT" not in instrument:
                    trading_symbol = f"{symbol_name}-{dd_mmm_yyyy}-FUT"
                elif "OPT" in instrument:
                    try:
                        st = float(strike_str)
                        st_str = str(int(st)) if st % 1 == 0 else str(st)
                    except (ValueError, TypeError):
                        st_str = strike_str
                    opt = "CE" if option_type_str in ("CE", "CA") else "PE" if option_type_str in ("PE", "PA") else ""
                    trading_symbol = f"{symbol_name}-{dd_mmm_yyyy}-{st_str}-{opt}" if opt else f"{symbol_name}-{dd_mmm_yyyy}-{st_str}"
            except Exception:
                pass

        expiry = None
        if expiry_str:
            try:
                expiry = datetime.strptime(expiry_str.split()[0], "%Y-%m-%d")
            except (ValueError, TypeError):
                pass

        strike = None
        if strike_str:
            try:
                strike = Decimal(strike_str)
            except (ValueError, TypeError):
                pass

        option_type = None
        if option_type_str in ("CE", "CA"):
            option_type = OptionType.CALL
        elif option_type_str in ("PE", "PA"):
            option_type = OptionType.PUT

        instrument_type = InstrumentType.FUTURE
        if "OPT" in instrument:
            instrument_type = InstrumentType.OPTION

        lot_size = _safe_float(row.get("LOT_SIZE"), 1)
        tick_size = _safe_float(row.get("TICK_SIZE"), 0.05)

        iid = to_instrument_id(
            symbol=trading_symbol,
            exchange=ExchangeId.MCX.value,
            instrument_type=instrument_type,
            underlying=symbol_name,
            expiry=expiry.date() if expiry else None,
            strike=strike,
            option_type=option_type,
        )
        inst = Instrument(
            instrument_id=iid,
            symbol=trading_symbol,
            exchange=ExchangeId.MCX,
            asset_class=AssetClass.COMMODITY,
            currency="INR",
            instrument_type=instrument_type,
            strike=strike,
            expiry=expiry,
            option_type=option_type,
            lot_size=Decimal(str(lot_size)),
            tick_size=Decimal(str(tick_size)),
        )
        if security_id:
            self._wire.register_security(
                iid,
                security_id,
                symbol=trading_symbol,
                exchange=ExchangeId.MCX.value,
                instrument_type=instrument_type.value if instrument_type else None,
                underlying=symbol_name,
                expiry=expiry.date().isoformat() if expiry else None,
                strike=str(strike) if strike is not None else None,
                option_type=option_type.value if option_type else None,
            )
        return inst

    def search(self, query: str) -> list[Instrument]:
        q = query.upper().strip()
        # Check index map first for bare symbols like NIFTY, BANKNIFTY
        from plugins.brokers.common.index_map import get_index_entry, is_index
        if is_index(q):
            entry = get_index_entry(q)
            exchange = "BSE" if entry and entry.upstox_segment == "BSE_INDEX" else "NSE"
            idx_inst = self._by_id.get(f"{exchange}:{q}")
            if idx_inst:
                return [idx_inst]
        return [i for i in self._by_id.values() if q in i.symbol.upper() or q in i.instrument_id.value.upper()]

    def resolve(self, instrument_id: InstrumentId) -> Instrument | None:
        return self._by_id.get(instrument_id.value)

    def _cleanup_old_cache(self, cache_dir: Path) -> None:
        now = time.time()
        cutoff = now - (_INSTRUMENT_CACHE_CLEANUP_DAYS * 24 * 3600)
        try:
            for path in cache_dir.glob("dhan-instruments-*.csv"):
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("Cache cleanup failed: %s", exc)


def _safe_float(val: Any, default: float) -> float:
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default
