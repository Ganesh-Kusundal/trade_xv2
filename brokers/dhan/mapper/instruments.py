"""Instrument catalog — CSV loader and in-memory catalog.

Design reference: Trade_J ``DhanInstrumentLoader`` + ``DhanInstrumentCatalog``
                  + ``DhanSymbolNormalizer`` + ``ContractSymbolNormalizer``.

Architecture
------------
* ``DhanInstrumentDefinition``  — immutable dataclass for a single instrument.
* ``DhanInstrumentLoader``      — downloads / parses Dhan's api-scrip-master.csv.
* ``DhanInstrumentCatalog``     — in-memory store with the 6 indexes required
                                   by the audit (securityId, tradingSymbol,
                                   customSymbol, ISIN, exchange, segment).
* ``DhanSymbolResolver``        — high-level symbol/string → definition,
                                   with structured errors (single / ambiguous
                                   / unknown).
* ``ContractSymbolNormalizer``  — Trade_J-port that parses/canonicalises
                                   F&O and equity symbols.

The catalog is the **single source of truth** for:
  - Resolving ``securityId`` (needed as ``UnderlyingScrip`` in REST calls)
  - Resolving ``ExchangeSegment`` (needed as ``UnderlyingSeg`` in REST calls)
  - Contract metadata: lot size, expiry, strike, option type

Live market data (prices, greeks, OI) always comes from the API endpoints.
"""

from __future__ import annotations

import csv
import fcntl
import hashlib
import io
import logging
import os
import re
import urllib.request
from collections.abc import Iterable
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from threading import RLock

from brokers.common.core.enums import ExchangeSegment
from brokers.common.core.instruments import InstrumentRegistry
from brokers.dhan.mapper.contract_symbol_normalizer import (
    build_canonical as _csn_build_canonical,
)
from brokers.dhan.mapper.contract_symbol_normalizer import (
    normalize as _csn_normalize,
)
from brokers.dhan.mapper.contract_symbol_normalizer import (
    parse as _csn_parse,
)
from brokers.dhan.mapper.dhan_segment_mapper import from_csv as _seg_from_csv
from brokers.dhan.mapper.dhan_segment_mapper import from_value as _seg_from_value
from brokers.dhan.mapper.dhan_segment_mapper import to_wire_value

logger = logging.getLogger(__name__)

# Dhan's official daily instrument master CSV — same URL as Trade_J
_INSTRUMENT_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"

# Column name aliases from Dhan's CSV header — normalised (lowercase, no _ / -)
# These match the exact normalisation performed by ``_normalise_col`` on the
# CSV header (e.g. ``SEM_SMST_SECURITY_ID`` → ``semsmstsecurityid``).
# Keep this list in sync with the CSV schema published by Dhan.
_COL_SECURITY_ID = ("semsmstsecurityid", "securityid", "security_id")
_COL_SYMBOL = ("semtradingsymbol", "symbol", "tradingsymbol")
_COL_CUSTOM_SYMBOL = ("semcustomsymbol", "canonicalsymbol", "canonical_symbol")
_COL_EXCHANGE_ID = ("semexmexchid", "exchange", "exchangeid")
_COL_SEGMENT = ("semsegment", "segment", "exchangesegment")
_COL_INSTRUMENT_TYPE = (
    "seminstrumentname",
    "instrumenttype",
    "instrumentname",
    "type",
)
_COL_EXPIRY = ("semexpirydate", "expiry", "expirydate")
_COL_STRIKE = ("semstrikeprice", "strikeprice", "strike")
_COL_OPTION_TYPE = ("semoptiontype", "optiontype", "option")
_COL_LOT_SIZE = ("semlotunits", "lotsize", "lotunits")
_COL_TICK_SIZE = ("semticksize", "ticksize")
_COL_UNDERLYING = (
    "semunderlyingsymbol",
    "underlyingsymbol",
    "underlying",
    "underlyingsym",
)
_COL_UNDERLYING_SECU = (
    "semunderlyingsecurityid",
    "underlyingsecurityid",
    "underlyingsecid",
)
_COL_SYMBOL_NAME = ("smsymbolname", "symbolname")
_COL_EXPIRY_FLAG = ("semexpiryflag", "expiryflag")
_COL_EXCH_INSTRUMENT_TYPE = (
    "semexchinstrumenttype",
    "exchinstrumenttype",
)
_COL_SERIES = ("semseries", "series")
_COL_ISIN = ("semisin", "isin")  # optional column, may be absent in CSV

_DATE_FMTS = ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y", "%m/%d/%Y %H:%M", "%d-%b-%Y")


def _normalise_col(name: str) -> str:
    """Normalise a CSV column name to a lookup key."""
    return name.strip().replace("_", "").replace("-", "").replace(" ", "").lower()


# Required columns that must exist in the snapshot for it to be considered
# well-formed.  The audit requires the loader to fail fast on corruption.
_REQUIRED_COLUMNS: set[str] = {
    _normalise_col(_COL_SECURITY_ID[0]),
    _normalise_col(_COL_SYMBOL[0]),
    _normalise_col(_COL_EXCHANGE_ID[0]),
    _normalise_col(_COL_SEGMENT[0]),
}


# ─── Domain model ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DhanInstrumentDefinition:
    """Immutable description of a single tradable instrument from Dhan's catalog."""

    symbol: str
    canonical_symbol: str
    exchange_segment: ExchangeSegment
    security_id: str
    instrument_type: str = "EQUITY"
    underlying: str = ""
    expiry: str | None = None  # ISO date string "YYYY-MM-DD"
    strike: Decimal | None = None  # in rupees (as Decimal)
    strike_price_paisa: int | None = None  # in paisa (for fast comparisons)
    option_type: str = ""  # "CE" | "PE" | ""
    lot_size: int = 0
    tick_size: Decimal = Decimal("0")
    underlying_security_id: str = ""
    isin: str = ""

    @property
    def is_option(self) -> bool:
        return self.instrument_type.upper() in {
            "OPTIONS",
            "OPTIDX",
            "OPTSTK",
            "OPTFUT",
            "OPTCUR",
        } or self.option_type.upper() in {"CE", "PE", "CALL", "PUT"}

    @property
    def is_future(self) -> bool:
        t = self.instrument_type.upper()
        return t.startswith("FUT") or t in {"FUTURES"}

    @property
    def is_index(self) -> bool:
        return (
            self.instrument_type.upper() == "INDEX"
            or self.exchange_segment == ExchangeSegment.IDX_I
        )

    @property
    def is_equity(self) -> bool:
        return self.instrument_type.upper() == "EQUITY"

    @property
    def is_currency(self) -> bool:
        t = self.instrument_type.upper()
        return "CUR" in t or self.exchange_segment in (
            ExchangeSegment.NSE_CURRENCY,
            ExchangeSegment.BSE_CURRENCY,
        )

    @property
    def is_commodity(self) -> bool:
        t = self.instrument_type.upper()
        return "COM" in t or self.exchange_segment == ExchangeSegment.MCX

    @property
    def exchange(self) -> str:
        """Canonical exchange short name (NSE / BSE / MCX)."""
        return {
            ExchangeSegment.NSE: "NSE",
            ExchangeSegment.BSE: "BSE",
            ExchangeSegment.NSE_FNO: "NSE",
            ExchangeSegment.BSE_FNO: "BSE",
            ExchangeSegment.MCX: "MCX",
            ExchangeSegment.NSE_CURRENCY: "NSE",
            ExchangeSegment.BSE_CURRENCY: "BSE",
            ExchangeSegment.IDX_I: "IDX",
        }[self.exchange_segment]

    def to_order_request(self, **overrides):
        from brokers.common.core.models import OrderRequest

        return OrderRequest(
            symbol=self.symbol,
            security_id=self.security_id,
            exchange_segment=self.exchange_segment,
            **overrides,
        )


# ─── Diagnostics result types ────────────────────────────────────────────────


@dataclass(frozen=True)
class CatalogDiagnostics:
    """Snapshot of catalog health for startup validation & operator diagnostics."""

    record_count: int = 0
    by_security_id_size: int = 0
    by_trading_symbol_size: int = 0
    by_custom_symbol_size: int = 0
    by_isin_size: int = 0
    by_exchange_size: int = 0
    by_segment_size: int = 0
    duplicate_security_ids: tuple[str, ...] = field(default_factory=tuple)
    duplicate_composite_keys: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)
    missing_isin_count: int = 0
    missing_exchange_count: int = 0
    futures_count: int = 0
    options_count: int = 0
    indices_count: int = 0
    equities_count: int = 0
    checksum: str = ""

    def to_report(self) -> str:
        """Human-readable diagnostic report (Rich / console friendly)."""
        lines = [
            "Catalog diagnostics:",
            f"  record count            = {self.record_count}",
            f"  by_security_id          = {self.by_security_id_size}",
            f"  by_trading_symbol       = {self.by_trading_symbol_size}",
            f"  by_custom_symbol        = {self.by_custom_symbol_size}",
            f"  by_isin                 = {self.by_isin_size}",
            f"  by_exchange             = {self.by_exchange_size}",
            f"  by_segment              = {self.by_segment_size}",
            f"  duplicate security ids  = {len(self.duplicate_security_ids)}",
            f"  missing isin            = {self.missing_isin_count}",
            f"  missing exchange        = {self.missing_exchange_count}",
            f"  futures                 = {self.futures_count}",
            f"  options                 = {self.options_count}",
            f"  indices                 = {self.indices_count}",
            f"  equities                = {self.equities_count}",
            f"  checksum                = {self.checksum}",
        ]
        return "\n".join(lines)


# ─── Snapshot validation ─────────────────────────────────────────────────────


@dataclass
class SnapshotValidationError(ValueError):
    """Raised when a Dhan snapshot is corrupt or incomplete."""

    path: Path
    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Snapshot validation failed for {self.path}: {self.message}"


def _file_checksum(path: Path) -> str:
    """SHA-256 of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@contextmanager
def _file_lock(lock_path: Path):
    """Cross-platform advisory file lock.

    On POSIX, uses ``fcntl.flock``.  On Windows, falls back to a sentinel
    file.  Either way, two concurrent ``ensure_daily_snapshot`` calls
    cannot both download / write the same path.
    """
    if os.name == "posix":
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "w") as lock_fh:
            try:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
    else:  # pragma: no cover - non-POSIX fallback
        # Best-effort sentinel: create-if-missing.
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fh = open(lock_path, "w")
        lock_fh.close()
        try:
            yield
        finally:
            with suppress(FileNotFoundError):
                lock_path.unlink()


# ─── Loader (CSV → definitions) ──────────────────────────────────────────────


class DhanInstrumentLoader:
    """Downloads and parses Dhan's instrument master CSV.

    Mirrors Trade_J's ``DhanInstrumentLoader.java``.

    The loader supports two modes:
    1. ``load(path)``                    — parse an existing CSV file.
    2. ``load_from_daily_cache(dir)``    — download-and-cache, parse today's snapshot.
    """

    INSTRUMENT_MASTER_URL = _INSTRUMENT_MASTER_URL

    # ── public API ──────────────────────────────────────────────────────────

    def load(self, path: Path) -> list[DhanInstrumentDefinition]:
        """Parse a CSV file from disk."""
        with open(path, newline="", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        if not lines:
            raise ValueError(f"Instrument catalog is empty: {path}")
        return self._parse_lines(lines)

    def load_from_daily_cache(
        self,
        cache_dir: Path,
        force_refresh: bool = False,
    ) -> list[DhanInstrumentDefinition]:
        """Ensure today's snapshot exists (download if needed), then parse it."""
        snapshot = self.ensure_daily_snapshot(cache_dir, force_refresh)
        validate_snapshot(snapshot)
        return self.load(snapshot)

    def ensure_daily_snapshot(
        self,
        cache_dir: Path,
        force_refresh: bool = False,
    ) -> Path:
        """Download the instrument master CSV if today's snapshot doesn't exist.

        Behaviour (audit-aligned):
        * Reuse today's existing snapshot unless ``force_refresh`` is True.
        * Refresh the snapshot if the existing file is empty.
        * Acquire an advisory file lock to prevent concurrent downloads.
        * Log: "Using cached instrument snapshot", "Downloading fresh
          instrument snapshot", "Snapshot record count", "Snapshot checksum",
          "Snapshot date".
        """
        cache_dir.mkdir(parents=True, exist_ok=True)
        snapshot = cache_dir / f"api-scrip-master-{date.today()}.csv"
        lock = cache_dir / ".snapshot.lock"

        with _file_lock(lock):
            if force_refresh:
                logger.info("Downloading fresh instrument snapshot (force_refresh=True)")
                self._download_to(snapshot)
            elif snapshot.exists() and snapshot.stat().st_size > 0:
                logger.info(
                    "Using cached instrument snapshot: %s (size=%d bytes)",
                    snapshot.name,
                    snapshot.stat().st_size,
                )
            else:
                logger.info("Downloading fresh instrument snapshot to %s", snapshot)
                self._download_to(snapshot)

        # Diagnostic logging after the file exists.
        try:
            checksum = _file_checksum(snapshot)
            logger.info("Snapshot date: %s", date.today().isoformat())
            logger.info("Snapshot checksum: %s", checksum)
            # Record count requires a quick line-count; cheapest is bytes / 200.
            with open(snapshot, "rb") as fh:
                line_count = sum(1 for _ in fh)
            logger.info("Snapshot record count: %d", line_count)
        except Exception as exc:  # pragma: no cover - diagnostics are best-effort
            logger.debug("Snapshot diagnostic logging failed: %s", exc)

        return snapshot

    def _download_to(self, snapshot: Path) -> None:
        """Download the master CSV to ``snapshot`` (overwriting)."""
        with urllib.request.urlopen(self.INSTRUMENT_MASTER_URL) as response:
            content = response.read()
        # Write atomically via temp file then rename.
        tmp = snapshot.with_suffix(snapshot.suffix + ".part")
        tmp.write_bytes(content)
        os.replace(tmp, snapshot)

    # ── parsing ─────────────────────────────────────────────────────────────

    def _parse_lines(self, lines: list[str]) -> list[DhanInstrumentDefinition]:
        """Parse CSV lines into DhanInstrumentDefinition objects."""
        reader = csv.reader(io.StringIO("".join(lines)))
        raw_headers = next(reader)
        # Normalise header names: lowercase, strip underscores and hyphens
        headers = [_normalise_col(h) for h in raw_headers]
        index: dict[str, int] = {h: i for i, h in enumerate(headers)}

        # Verify required columns are present (audit §7).
        missing = _REQUIRED_COLUMNS - set(index)
        if missing:
            raise SnapshotValidationError(
                Path("<in-memory>"),
                f"Required columns missing from snapshot: {sorted(missing)}",
            )

        definitions: list[DhanInstrumentDefinition] = []
        for row in reader:
            if not any(c.strip() for c in row):
                continue
            defn = self._parse_row(index, row)
            if defn is not None:
                definitions.append(defn)

        if not definitions:
            raise ValueError("Instrument catalog yielded no resolvable instruments")
        return definitions

    def _parse_row(
        self, index: dict[str, int], cells: list[str]
    ) -> DhanInstrumentDefinition | None:
        security_id = self._required(index, cells, _COL_SECURITY_ID)
        symbol = self._required(index, cells, _COL_SYMBOL)
        custom_symbol = self._first(index, cells, _COL_CUSTOM_SYMBOL)
        exchange_id = self._first(index, cells, _COL_EXCHANGE_ID)
        raw_segment = self._first(index, cells, _COL_SEGMENT)

        # Resolve segment — try combined CSV key first, then raw value
        segment: ExchangeSegment | None = None
        if exchange_id and raw_segment:
            segment = _seg_from_csv(exchange_id, raw_segment)
        if segment is None and raw_segment:
            segment = _seg_from_value(raw_segment)
        if segment is None:
            return None  # skip unknown segments

        instrument_type = self._first(index, cells, _COL_INSTRUMENT_TYPE).upper() or "EQUITY"
        expiry_str = self._first(index, cells, _COL_EXPIRY)
        expiry = _parse_date(expiry_str)
        strike_str = self._first(index, cells, _COL_STRIKE)
        strike = _parse_decimal(strike_str)
        strike_paisa = _parse_strike_paisa(strike_str)
        option_type = self._first(index, cells, _COL_OPTION_TYPE).upper()
        lot_size = _parse_int(self._first(index, cells, _COL_LOT_SIZE), default=0)
        tick_size = _parse_decimal(self._first(index, cells, _COL_TICK_SIZE)) or Decimal("0")
        underlying = self._resolve_underlying(index, cells, custom_symbol, symbol, instrument_type)
        underlying_sec_id = self._first(index, cells, _COL_UNDERLYING_SECU)
        isin = self._first(index, cells, _COL_ISIN)
        canonical = self._make_canonical(
            symbol,
            custom_symbol,
            instrument_type,
            underlying,
            expiry,
            strike_paisa,
            option_type,
        )

        return DhanInstrumentDefinition(
            symbol=symbol.strip(),
            canonical_symbol=canonical,
            exchange_segment=segment,
            security_id=security_id.strip(),
            instrument_type=instrument_type,
            underlying=underlying,
            expiry=expiry,
            strike=strike,
            strike_price_paisa=strike_paisa,
            option_type=option_type,
            lot_size=lot_size,
            tick_size=tick_size,
            underlying_security_id=underlying_sec_id.strip(),
            isin=isin,
        )

    def _resolve_underlying(
        self,
        index: dict[str, int],
        cells: list[str],
        custom_symbol: str,
        symbol: str,
        instrument_type: str,
    ) -> str:
        direct = self._first(index, cells, _COL_UNDERLYING)
        if direct:
            return _normalise_underlying(direct)
        from_custom = _normalise_underlying(custom_symbol)
        if from_custom:
            return from_custom
        if instrument_type.upper().startswith("FUT"):
            # Extract underlying from trading symbol (e.g. "NIFTY25JUNFUT" → "NIFTY")
            return (
                _csn_parse(symbol) and _csn_parse(symbol).underlying
            ) or _extract_future_underlying(symbol)
        return ""

    def _make_canonical(
        self,
        symbol: str,
        custom_symbol: str,
        instrument_type: str,
        underlying: str,
        expiry: str | None,
        strike_paisa: int | None,
        option_type: str,
    ) -> str:
        t = instrument_type.upper()
        if option_type in {"CE", "PE", "CALL", "PUT"} and expiry and strike_paisa is not None:
            # Use the Trade_J-style canonical option symbol
            return _csn_build_canonical(
                underlying or symbol,
                date.fromisoformat(expiry),
                strike_paisa,
                option_type,
                is_option=True,
            )
        if t.startswith("FUT") and underlying and expiry:
            return _csn_build_canonical(
                underlying,
                date.fromisoformat(expiry),
                None,
                None,
                is_option=False,
            )
        if t == "INDEX":
            # Use custom_symbol as canonical for indices (e.g. "NIFTY 50")
            return (custom_symbol or symbol).strip().upper()
        cand = custom_symbol or symbol
        return cand.strip().upper()

    def _required(self, index: dict[str, int], cells: list[str], names: tuple) -> str:
        val = self._first(index, cells, names)
        if not val:
            raise ValueError(f"Missing required column value for {names}")
        return val

    def _first(self, index: dict[str, int], cells: list[str], names: tuple) -> str:
        for name in names:
            col = index.get(_normalise_col(name))
            if col is not None and col < len(cells):
                val = cells[col].strip().strip('"')
                if val:
                    return val
        return ""


# ─── Catalog (in-memory lookup) ───────────────────────────────────────────────


class DhanInstrumentCatalog:
    """Thread-safe in-memory instrument catalog with the 6 audit-required indexes.

    Mirrors Trade_J's ``DhanInstrumentCatalog.java``.

    Indexes maintained
    ------------------
    _by_security_id        : securityId              → definition
    _by_trading_symbol     : TRADING_SYMBOL (upper)  → list[definition]
    _by_custom_symbol      : CUSTOM_SYMBOL  (upper)  → list[definition]
    _by_isin               : ISIN                    → definition
    _by_exchange           : exchange (NSE/BSE/MCX)  → list[definition]
    _by_segment            : ExchangeSegment         → list[definition]
    _by_symbol             : "<WIRE_SEGMENT>::<SYMBOL_UPPER>" → definition
    _futures_by_underlying : UNDERLYING_UPPER        → list[definition] sorted by expiry
    _options_by_underlying : UNDERLYING_UPPER        → list[definition] sorted by expiry/strike
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._by_symbol: dict[str, DhanInstrumentDefinition] = {}
        self._by_security_id: dict[str, DhanInstrumentDefinition] = {}
        self._by_trading_symbol: dict[str, list[DhanInstrumentDefinition]] = {}
        self._by_custom_symbol: dict[str, list[DhanInstrumentDefinition]] = {}
        self._by_isin: dict[str, DhanInstrumentDefinition] = {}
        self._by_exchange: dict[str, list[DhanInstrumentDefinition]] = {}
        self._by_segment: dict[ExchangeSegment, list[DhanInstrumentDefinition]] = {}
        self._futures_by_underlying: dict[str, list[DhanInstrumentDefinition]] = {}
        self._options_by_underlying: dict[str, list[DhanInstrumentDefinition]] = {}
        self._loader = DhanInstrumentLoader()
        self._loaded = False
        self._last_loaded_path: Path | None = None

    # ── loading ──────────────────────────────────────────────────────────────

    def load(self, path: Path) -> None:
        """Load catalog from an existing CSV file."""
        self.replace_all(self._loader.load(path))
        self._last_loaded_path = path

    def load_from_daily_cache(
        self,
        cache_dir: Path,
        force_refresh: bool = False,
    ) -> None:
        """Download today's CSV (if needed) and load it.

        F11 (M3): Previously this method dropped the loader's result on the
        floor — it stored the snapshot *path* but never built the in-memory
        indexes, leaving ``get_definition()`` permanently returning ``None``
        for any symbol.  We now route through :meth:`load` (which itself
        calls :meth:`replace_all` after the loader parses) so the indexes
        are populated for every code path that uses this entry point.
        """
        snapshot = self._loader.ensure_daily_snapshot(cache_dir, force_refresh)
        self.load(snapshot)

    def ensure_snapshot(self, cache_dir: Path, force_refresh: bool = False) -> Path:
        """Return path to today's cached snapshot (downloading if needed)."""
        return self._loader.ensure_daily_snapshot(cache_dir, force_refresh)

    def replace_all(self, definitions: list[DhanInstrumentDefinition]) -> None:
        """Atomically replace the entire catalog (mirrors Trade_J's replaceAll).

        Builds all 6 audit-required indexes plus the futures/options sub-indexes
        used by the option-chain adapter.
        """
        with self._lock:
            new_by_symbol: dict[str, DhanInstrumentDefinition] = {}
            new_by_id: dict[str, DhanInstrumentDefinition] = {}
            new_by_trading: dict[str, list[DhanInstrumentDefinition]] = {}
            new_by_custom: dict[str, list[DhanInstrumentDefinition]] = {}
            new_by_isin: dict[str, DhanInstrumentDefinition] = {}
            new_by_exchange: dict[str, list[DhanInstrumentDefinition]] = {}
            new_by_segment: dict[ExchangeSegment, list[DhanInstrumentDefinition]] = {}
            new_futures: dict[str, list[DhanInstrumentDefinition]] = {}
            new_options: dict[str, list[DhanInstrumentDefinition]] = {}

            for defn in definitions:
                wire = _safe_wire(defn.exchange_segment)
                if wire is None:
                    continue

                # Composite (wire::symbol) key for direct, case-insensitive lookups.
                for alias in _symbol_aliases(defn):
                    key = f"{wire}::{alias.upper()}"
                    new_by_symbol.setdefault(key, defn)

                # 1) securityId — must be unique
                if defn.security_id:
                    new_by_id[defn.security_id] = defn

                # 2) trading symbol (multiple instruments may share a symbol
                #    across NSE / BSE — store as list).
                if defn.symbol:
                    _append_to(new_by_trading, defn.symbol.upper(), defn)

                # 3) custom symbol
                if defn.canonical_symbol:
                    _append_to(new_by_custom, defn.canonical_symbol.upper(), defn)

                # 4) ISIN (when present in the source)
                if defn.isin:
                    new_by_isin[defn.isin] = defn

                # 5) exchange
                _append_to(new_by_exchange, defn.exchange, defn)

                # 6) segment
                _append_to(new_by_segment, defn.exchange_segment, defn)

                # Index futures and options by underlying
                if defn.is_future and defn.underlying:
                    _append_to(new_futures, defn.underlying.upper(), defn)
                if defn.is_option and defn.underlying:
                    _append_to(new_options, defn.underlying.upper(), defn)

            # Sort by expiry
            for k in new_futures:
                new_futures[k] = sorted(
                    new_futures[k],
                    key=lambda d: d.expiry or "9999-12-31",
                )
            for k in new_options:
                new_options[k] = sorted(
                    new_options[k],
                    key=lambda d: (
                        d.expiry or "9999-12-31",
                        d.strike_price_paisa or 0,
                        d.option_type,
                    ),
                )

            # Atomic swap (Lock guarantees the assignment is a single statement)
            self._by_symbol = new_by_symbol
            self._by_security_id = new_by_id
            self._by_trading_symbol = new_by_trading
            self._by_custom_symbol = new_by_custom
            self._by_isin = new_by_isin
            self._by_exchange = new_by_exchange
            self._by_segment = new_by_segment
            self._futures_by_underlying = new_futures
            self._options_by_underlying = new_options
            self._loaded = True

    # ── properties ───────────────────────────────────────────────────────────

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def size(self) -> int:
        return len(self._by_security_id)

    @property
    def last_loaded_path(self) -> Path | None:
        return self._last_loaded_path

    # ── diagnostics ──────────────────────────────────────────────────────────

    def diagnostics(self) -> CatalogDiagnostics:
        """Compute a full diagnostic snapshot of the catalog.

        Used by the ``validate_snapshot`` startup check and by the
        ``instruments lookup`` CLI for sanity output.
        """
        with self._lock:
            sid_counts: dict[str, int] = {}
            missing_isin = 0
            missing_exchange = 0
            futures = options = indices = equities = 0
            for defn in self._by_security_id.values():
                sid_counts[defn.security_id] = sid_counts.get(defn.security_id, 0) + 1
                if not defn.isin:
                    missing_isin += 1
                if not defn.exchange:
                    missing_exchange += 1
                if defn.is_future:
                    futures += 1
                elif defn.is_option:
                    options += 1
                elif defn.is_index:
                    indices += 1
                elif defn.is_equity:
                    equities += 1
            duplicate_sids = tuple(sid for sid, count in sid_counts.items() if count > 1)
            checksum = ""
            if self._last_loaded_path is not None and self._last_loaded_path.exists():
                try:
                    checksum = _file_checksum(self._last_loaded_path)
                except OSError:
                    checksum = "<unreadable>"
            return CatalogDiagnostics(
                record_count=len(self._by_security_id),
                by_security_id_size=len(self._by_security_id),
                by_trading_symbol_size=len(self._by_trading_symbol),
                by_custom_symbol_size=len(self._by_custom_symbol),
                by_isin_size=len(self._by_isin),
                by_exchange_size=len(self._by_exchange),
                by_segment_size=len(self._by_segment),
                duplicate_security_ids=duplicate_sids,
                missing_isin_count=missing_isin,
                missing_exchange_count=missing_exchange,
                futures_count=futures,
                options_count=options,
                indices_count=indices,
                equities_count=equities,
                checksum=checksum,
            )

    # ── lookup by symbol + segment ────────────────────────────────────────────

    def get_definition(
        self,
        symbol: str,
        exchange_segment: ExchangeSegment,
    ) -> DhanInstrumentDefinition | None:
        """Look up by symbol + segment (case-insensitive). Returns None if not found.

        Tries the canonical form first, then the stripped form (Trade_J
        ``ContractSymbolNormalizer.stripped`` equivalent), then the lowercased
        segment alias.
        """
        wire = _safe_wire(exchange_segment)
        if wire is None:
            return None
        sym = _csn_normalize(symbol).upper()
        with self._lock:
            found = self._by_symbol.get(f"{wire}::{sym}")
            if found is not None:
                return found
            # Try the "stripped" form (no spaces/dashes/underscores) — for
            # compact aliases like "NIFTY30JUN25000CE" or "RELIANCE25JUNFUT".
            stripped = _strip_separators(sym)
            return self._by_symbol.get(f"{wire}::{stripped}")

    def require_definition(
        self,
        symbol: str,
        exchange_segment: ExchangeSegment,
    ) -> DhanInstrumentDefinition:
        """Look up by symbol + segment. Raises ValueError if not found."""
        defn = self.get_definition(symbol, exchange_segment)
        if defn is None:
            raise ValueError(
                f"No Dhan instrument mapping for symbol={symbol!r} on segment={exchange_segment!r}"
            )
        return defn

    # ── lookup by security ID ─────────────────────────────────────────────────

    def get_by_security_id(self, security_id: str) -> DhanInstrumentDefinition | None:
        with self._lock:
            return self._by_security_id.get(str(security_id))

    def require_by_security_id(self, security_id: str) -> DhanInstrumentDefinition:
        defn = self.get_by_security_id(security_id)
        if defn is None:
            raise ValueError(f"No Dhan instrument mapping for securityId={security_id!r}")
        return defn

    # ── bulk lookups by audit-required indexes ───────────────────────────────

    def find_by_trading_symbol(self, trading_symbol: str) -> list[DhanInstrumentDefinition]:
        """All instruments that share the given trading symbol (any segment)."""
        with self._lock:
            return list(self._by_trading_symbol.get(trading_symbol.upper(), []))

    def find_by_custom_symbol(self, custom_symbol: str) -> list[DhanInstrumentDefinition]:
        with self._lock:
            return list(self._by_custom_symbol.get(custom_symbol.upper(), []))

    def find_by_isin(self, isin: str) -> DhanInstrumentDefinition | None:
        with self._lock:
            return self._by_isin.get(isin)

    def find_by_exchange(self, exchange: str) -> list[DhanInstrumentDefinition]:
        with self._lock:
            return list(self._by_exchange.get(exchange.upper(), []))

    def find_by_segment(self, segment: ExchangeSegment) -> list[DhanInstrumentDefinition]:
        with self._lock:
            return list(self._by_segment.get(segment, []))

    # ── underlying resolution for option chain ────────────────────────────────

    def resolve_underlying(
        self,
        symbol: str,
        exchange_segment: ExchangeSegment,
    ) -> DhanInstrumentDefinition:
        """Resolve the underlying instrument definition.

        Mirrors Trade_J's DhanOptionsAdapter.resolveUnderlying():
        - For NSE_FNO: try IDX_I → NSE_EQ → NSE_FNO
        - For BSE_FNO: try IDX_I → BSE_EQ → BSE_FNO
        - For MCX: use nearest futures contract
        - Others: direct lookup
        """
        # First try the direct lookup chain
        for candidate in _lookup_segments(exchange_segment):
            defn = self.get_definition(symbol, candidate)
            if defn is not None:
                return defn
        # MCX supports contract discovery
        if exchange_segment == ExchangeSegment.MCX:
            try:
                return self.nearest_futures_contract(symbol, exchange_segment)
            except ValueError:
                pass
        raise ValueError(
            f"Unable to resolve underlying {symbol!r} for option-chain segment {exchange_segment!r}"
        )

    # ── futures ───────────────────────────────────────────────────────────────

    def futures_contracts(
        self,
        underlying: str,
        exchange_segment: ExchangeSegment | None = None,
    ) -> list[DhanInstrumentDefinition]:
        """Return all live futures contracts for an underlying."""
        with self._lock:
            candidates = list(self._futures_by_underlying.get(underlying.strip().upper(), []))
        if exchange_segment is None:
            return candidates
        allowed = _candidate_derivative_segments(exchange_segment)
        return [d for d in candidates if d.exchange_segment in allowed]

    def nearest_futures_contract(
        self,
        underlying: str,
        exchange_segment: ExchangeSegment | None = None,
    ) -> DhanInstrumentDefinition:
        today = date.today().isoformat()
        futures = [
            d
            for d in self.futures_contracts(underlying, exchange_segment)
            if d.expiry is None or d.expiry >= today
        ]
        if not futures:
            raise ValueError(f"No live futures contract for {underlying!r} on {exchange_segment!r}")
        return futures[0]

    def futures_expiries(
        self,
        underlying: str,
        exchange_segment: ExchangeSegment | None = None,
    ) -> list[str]:
        return sorted(
            {
                d.expiry
                for d in self.futures_contracts(underlying, exchange_segment)
                if d.expiry is not None
            }
        )

    # ── options ───────────────────────────────────────────────────────────────

    def option_contracts(
        self,
        underlying: str,
        exchange_segment: ExchangeSegment | None = None,
        expiry: str | None = None,
    ) -> list[DhanInstrumentDefinition]:
        """Return option contracts matching underlying/segment/expiry filters."""
        with self._lock:
            candidates = list(self._options_by_underlying.get(underlying.strip().upper(), []))
        if exchange_segment is not None:
            allowed = _candidate_derivative_segments(exchange_segment)
            candidates = [d for d in candidates if d.exchange_segment in allowed]
        if expiry is not None:
            candidates = [d for d in candidates if d.expiry == expiry]
        return candidates

    def option_expiries(
        self,
        underlying: str,
        exchange_segment: ExchangeSegment | None = None,
    ) -> list[str]:
        today = date.today().isoformat()
        return sorted(
            {
                d.expiry
                for d in self.option_contracts(underlying, exchange_segment)
                if d.expiry is not None and d.expiry >= today
            }
        )

    def find_option_contract(
        self,
        underlying: str,
        exchange_segment: ExchangeSegment | None,
        expiry: str,
        strike_paisa: int,
        option_type: str,  # "CE" or "PE"
    ) -> DhanInstrumentDefinition | None:
        """Find a specific option contract by exact match."""
        ot = option_type.strip().upper()
        for d in self.option_contracts(underlying, exchange_segment, expiry):
            if d.strike_price_paisa == strike_paisa and d.option_type.upper() == ot:
                return d
        return None

    # ── resolve security_id for API calls ─────────────────────────────────────

    def resolve_security_id(self, symbol: str, exchange: str) -> str:
        """Resolve the numeric security ID string for a symbol.

        Tries the catalog first; falls back to InstrumentRegistry for seed instruments.
        """
        segment = _seg_from_value(exchange)
        if segment is not None:
            defn = self.get_definition(symbol, segment)
            if defn is not None:
                return defn.security_id
            # Try the lookup-segments fallback chain
            for candidate in _lookup_segments(segment):
                defn = self.get_definition(symbol, candidate)
                if defn is not None:
                    return defn.security_id
        # Fall back to InstrumentRegistry (seed instruments)
        try:
            return InstrumentRegistry().broker_identifier(symbol.upper(), exchange.upper())
        except KeyError:
            raise ValueError(
                f"No instrument registered for symbol={symbol!r} exchange={exchange!r}"
            )

    def segment_from_exchange(self, exchange: str) -> ExchangeSegment:
        """Resolve ExchangeSegment from a canonical exchange string (public)."""
        seg = _seg_from_value(exchange)
        if seg is None:
            raise ValueError(f"Unknown exchange segment: {exchange!r}")
        return seg

    # Backward-compat alias (private) — many call-sites still use the
    # underscored form from earlier refactors.
    def _segment_from_exchange(self, exchange: str) -> ExchangeSegment:
        return self.segment_from_exchange(exchange)

    # ── payload resolution (WebSocket / REST JSON unwrap) ─────────────────────

    def resolve_payload(self, payload) -> DhanInstrumentDefinition | None:
        """Resolve a Dhan WebSocket / JSON payload to a definition.

        Mirrors Trade_J's ``DhanInstrumentCatalog.resolveDhanPayload``.
        Accepts:
        * a dict with ``securityId`` and/or ``tradingSymbol``/``exchangeSegment``
        * a dict with ``tradingSymbol`` + ``exchange`` (legacy)
        """
        if payload is None:
            return None
        # Dict-like payloads
        if isinstance(payload, dict):
            sid = payload.get("securityId") or payload.get("security_id")
            if sid:
                defn = self.get_by_security_id(str(sid))
                if defn is not None:
                    return defn
            ts = payload.get("tradingSymbol") or payload.get("symbol")
            es = payload.get("exchangeSegment") or payload.get("exchange_segment")
            if ts and es:
                seg = _seg_from_value(str(es))
                if seg is not None:
                    defn = self.get_definition(str(ts), seg)
                    if defn is not None:
                        return defn
            exch = payload.get("exchange")
            if ts and exch:
                seg = _seg_from_value(str(exch))
                if seg is not None:
                    defn = self.get_definition(str(ts), seg)
                    if defn is not None:
                        return defn
            return None
        # Object-like payloads (duck-typed SDK objects)
        for attr in ("getSecurityId", "security_id", "securityId"):
            sid = getattr(payload, attr, None)
            if callable(sid):
                try:
                    sid = sid()
                except Exception:  # pragma: no cover
                    sid = None
            if sid:
                defn = self.get_by_security_id(str(sid))
                if defn is not None:
                    return defn
        for ts_attr in (
            "getTradingSymbol",
            "trading_symbol",
            "tradingSymbol",
            "symbol",
        ):
            ts = getattr(payload, ts_attr, None)
            if callable(ts):
                try:
                    ts = ts()
                except Exception:  # pragma: no cover
                    ts = None
            if not ts:
                continue
            for es_attr in (
                "getExchangeSegment",
                "exchange_segment",
                "exchangeSegment",
            ):
                es = getattr(payload, es_attr, None)
                if callable(es):
                    try:
                        es = es()
                    except Exception:  # pragma: no cover
                        es = None
                if es:
                    seg = _seg_from_value(str(es))
                    if seg is not None:
                        defn = self.get_definition(str(ts), seg)
                        if defn is not None:
                            return defn
            for ex_attr in ("getExchange", "exchange"):
                ex = getattr(payload, ex_attr, None)
                if callable(ex):
                    try:
                        ex = ex()
                    except Exception:  # pragma: no cover
                        ex = None
                if ex:
                    seg = _seg_from_value(str(ex))
                    if seg is not None:
                        defn = self.get_definition(str(ts), seg)
                        if defn is not None:
                            return defn
        return None


# ─── DhanInstrumentResolver (legacy alias) ────────────────────────────────────


class DhanInstrumentResolver(DhanInstrumentCatalog):
    """Legacy alias for DhanInstrumentCatalog.

    Pre-existing broker.py code references DhanInstrumentResolver; this alias
    preserves that while the catalog provides the full Trade_J-aligned API.
    """

    # ── Seed instruments (fallback when catalog not yet loaded) ──────────────
    from brokers.dhan.mapper.seed_security_ids import (
        DHAN_SEED_SECURITY_IDS,
    )

    _SEED_SECURITY_IDS: dict[tuple[str, str], str] = dict(DHAN_SEED_SECURITY_IDS)

    def __init__(self, service: Any | None = None) -> None:
        self._service = service
        self._lock_internal = RLock()
        self._by_symbol_internal: dict[str, DhanInstrumentDefinition] = {}
        self._by_security_id_internal: dict[str, DhanInstrumentDefinition] = {}
        self._by_trading_symbol_internal: dict[str, list[DhanInstrumentDefinition]] = {}
        self._by_custom_symbol_internal: dict[str, list[DhanInstrumentDefinition]] = {}
        self._by_isin_internal: dict[str, DhanInstrumentDefinition] = {}
        self._by_exchange_internal: dict[str, list[DhanInstrumentDefinition]] = {}
        self._by_segment_internal: dict[ExchangeSegment, list[DhanInstrumentDefinition]] = {}
        self._futures_by_underlying_internal: dict[str, list[DhanInstrumentDefinition]] = {}
        self._options_by_underlying_internal: dict[str, list[DhanInstrumentDefinition]] = {}
        self._loaded_internal = False
        self._last_loaded_path_internal: Path | None = None
        super().__init__()

    @property
    def _lock(self):
        return self._service._indexes.catalog._lock if self._service else self._lock_internal

    @_lock.setter
    def _lock(self, value):
        if self._service is None:
            self._lock_internal = value

    @property
    def _by_symbol(self):
        return (
            self._service._indexes.catalog._by_symbol if self._service else self._by_symbol_internal
        )

    @_by_symbol.setter
    def _by_symbol(self, value):
        if self._service is None:
            self._by_symbol_internal = value

    @property
    def _by_security_id(self):
        return (
            self._service._indexes.catalog._by_security_id
            if self._service
            else self._by_security_id_internal
        )

    @_by_security_id.setter
    def _by_security_id(self, value):
        if self._service is None:
            self._by_security_id_internal = value

    @property
    def _by_trading_symbol(self):
        return (
            self._service._indexes.catalog._by_trading_symbol
            if self._service
            else self._by_trading_symbol_internal
        )

    @_by_trading_symbol.setter
    def _by_trading_symbol(self, value):
        if self._service is None:
            self._by_trading_symbol_internal = value

    @property
    def _by_custom_symbol(self):
        return (
            self._service._indexes.catalog._by_custom_symbol
            if self._service
            else self._by_custom_symbol_internal
        )

    @_by_custom_symbol.setter
    def _by_custom_symbol(self, value):
        if self._service is None:
            self._by_custom_symbol_internal = value

    @property
    def _by_isin(self):
        return self._service._indexes.catalog._by_isin if self._service else self._by_isin_internal

    @_by_isin.setter
    def _by_isin(self, value):
        if self._service is None:
            self._by_isin_internal = value

    @property
    def _by_exchange(self):
        return (
            self._service._indexes.catalog._by_exchange
            if self._service
            else self._by_exchange_internal
        )

    @_by_exchange.setter
    def _by_exchange(self, value):
        if self._service is None:
            self._by_exchange_internal = value

    @property
    def _by_segment(self):
        return (
            self._service._indexes.catalog._by_segment
            if self._service
            else self._by_segment_internal
        )

    @_by_segment.setter
    def _by_segment(self, value):
        if self._service is None:
            self._by_segment_internal = value

    @property
    def _futures_by_underlying(self):
        return (
            self._service._indexes.catalog._futures_by_underlying
            if self._service
            else self._futures_by_underlying_internal
        )

    @_futures_by_underlying.setter
    def _futures_by_underlying(self, value):
        if self._service is None:
            self._futures_by_underlying_internal = value

    @property
    def _options_by_underlying(self):
        return (
            self._service._indexes.catalog._options_by_underlying
            if self._service
            else self._options_by_underlying_internal
        )

    @_options_by_underlying.setter
    def _options_by_underlying(self, value):
        if self._service is None:
            self._options_by_underlying_internal = value

    @property
    def _loaded(self):
        return self._service._indexes.catalog._loaded if self._service else self._loaded_internal

    @_loaded.setter
    def _loaded(self, value):
        if self._service is None:
            self._loaded_internal = value

    @property
    def _last_loaded_path(self):
        return (
            self._service._indexes.catalog._last_loaded_path
            if self._service
            else self._last_loaded_path_internal
        )

    @_last_loaded_path.setter
    def _last_loaded_path(self, value):
        if self._service is None:
            self._last_loaded_path_internal = value

    def resolve_security_id(self, symbol: str, exchange: str) -> str:
        """Resolve security ID — catalog first, seed table second."""
        # Try catalog (full CSV)
        try:
            return super().resolve_security_id(symbol, exchange)
        except (ValueError, KeyError):
            pass

        # Seed fallback with segment lookup chain
        symbol_upper = symbol.strip().upper()
        exchange_upper = exchange.strip().upper()
        segment = _seg_from_value(exchange_upper)

        # Determine candidates to check
        candidates = []
        if segment is not None:
            for cand_seg in _lookup_segments(segment):
                # map candidate ExchangeSegment to possible seed exchange keys
                if cand_seg == ExchangeSegment.IDX_I:
                    candidates.extend(["IDX_I", "IDX"])
                elif cand_seg == ExchangeSegment.NSE:
                    candidates.extend(["NSE", "NSE_EQ"])
                elif cand_seg == ExchangeSegment.NSE_FNO:
                    candidates.extend(["NSE_FNO", "NFO"])
                elif cand_seg == ExchangeSegment.BSE:
                    candidates.extend(["BSE", "BSE_EQ"])
                elif cand_seg == ExchangeSegment.BSE_FNO:
                    candidates.extend(["BSE_FNO", "BFO"])
                else:
                    candidates.append(cand_seg.name)

        # Add the original input exchange just in case
        if exchange_upper not in candidates:
            candidates.append(exchange_upper)

        for cand_exch in candidates:
            key = (symbol_upper, cand_exch)
            sid = self._SEED_SECURITY_IDS.get(key)
            if sid:
                return sid

        raise ValueError(
            f"No security ID for symbol={symbol!r} exchange={exchange!r}. "
            "Load the instrument catalog with load_instrument_catalog() first."
        )

    def load_catalog_definitions(self, path: Path) -> list[DhanInstrumentDefinition]:
        """Load CSV catalog and return the list of definitions (legacy API)."""
        if self._service is not None:
            self._service.load_snapshot(path)
            return list(self._service._indexes.catalog._by_security_id.values())
        defs = self._loader.load(path)
        self.replace_all(defs)
        return defs

    def load_catalog(self, path: Path) -> None:
        """Load CSV catalog from path."""
        if self._service is not None:
            self._service.load_snapshot(path)
        else:
            self.load(path)

    def lookup(
        self,
        *,
        security_id: str | None = None,
        symbol: str | None = None,
        exchange_segment: ExchangeSegment | None = None,
    ) -> DhanInstrumentDefinition | None:
        if security_id:
            return self.get_by_security_id(security_id)
        if symbol and exchange_segment:
            return self.get_definition(symbol, exchange_segment)
        return None

    def require(
        self,
        *,
        security_id: str | None = None,
        symbol: str | None = None,
        exchange_segment: ExchangeSegment | None = None,
    ) -> DhanInstrumentDefinition:
        defn = self.lookup(
            security_id=security_id,
            symbol=symbol,
            exchange_segment=exchange_segment,
        )
        if defn is None:
            raise ValueError(
                f"No instrument found: security_id={security_id!r}, "
                f"symbol={symbol!r}, segment={exchange_segment!r}"
            )
        return defn


# ─── Symbol resolver (high-level string → definition) ────────────────────────


@dataclass(frozen=True)
class ResolutionResult:
    """Outcome of a :class:`DhanSymbolResolver` call.

    Three flavours:
    * ``status == "single"``  — ``definition`` is the unique match.
    * ``status == "ambiguous"`` — ``candidates`` lists the possible matches.
    * ``status == "unknown"``  — symbol not in catalog; ``reason`` explains.
    """

    status: str
    definition: DhanInstrumentDefinition | None = None
    candidates: tuple[DhanInstrumentDefinition, ...] = ()
    reason: str = ""

    @property
    def is_single(self) -> bool:
        return self.status == "single"

    @property
    def is_ambiguous(self) -> bool:
        return self.status == "ambiguous"

    @property
    def is_unknown(self) -> bool:
        return self.status == "unknown"


class DhanSymbolResolver:
    """High-level string → DhanInstrumentDefinition resolver.

    Accepts every form the audit specifies::

        RELIANCE                       (bare equity / index)
        NSE:RELIANCE                   (wire segment prefix)
        NSE_EQ:RELIANCE                (canonical segment prefix)
        RELIANCE-EQ                    (legacy ``-EQ`` suffix)
        NIFTY 50                       (spaced index name)
        BANKNIFTY                      (alias for IDX_I lookup)
        SENSEX                         (alias for BSE index)
        RELIANCE FUT                   (future with bare name)
        RELIANCE 25 JUN FUT            (spaced future)
        RELIANCE25JUNFUT               (compact future)
        NIFTY 25000 CE                 (option, bare underlying)
        NIFTY 30 JUN 25000 CE          (option, full)
        NIFTY30JUN25000CE              (option, compact)
        BANKNIFTY 25 JUN 56000 PE      (option, full)
        NSE_FNO:RELIANCE25JUNFUT       (wire segment + compact future)

    Behaviour
    ---------
    * Always returns a :class:`ResolutionResult` — never raises, never
      silently picks the first match.
    * For ambiguous input (e.g. ``RELIANCE`` on both NSE and BSE), the
      ``status`` is ``"ambiguous"`` and ``candidates`` lists both.
    * For unknown input, the ``status`` is ``"unknown"`` with a
      structured ``reason``.
    """

    # Exchanges / segments that can appear as a ``<PREFIX>:<SYMBOL>`` lead-in.
    _SEGMENT_PREFIXES = (
        "NSE_EQ",
        "NSE_FNO",
        "BSE_EQ",
        "BSE_FNO",
        "NSE",
        "BSE",
        "NFO",
        "BFO",
        "MCX",
        "MCX_COMM",
        "IDX",
        "IDX_I",
        "INDEX",
        "CDS",
        "NSE_CURRENCY",
        "BSE_CURRENCY",
    )

    def __init__(self, catalog: DhanInstrumentCatalog) -> None:
        self._catalog = catalog

    def resolve(self, raw: str) -> ResolutionResult:
        """Resolve a raw user-supplied symbol string."""
        if not raw or not raw.strip():
            return ResolutionResult(status="unknown", reason="empty input")
        text = raw.strip()
        prefix, _, body = text.partition(":")
        if body and prefix.upper() in self._SEGMENT_PREFIXES:
            seg = _seg_from_value(prefix)
            if seg is None:
                return ResolutionResult(
                    status="unknown",
                    reason=f"unknown segment prefix: {prefix!r}",
                )
            return self._resolve_segmented(body, seg)

        # Strip legacy ``-EQ`` / ``-BE`` suffix (Trade_J compatibility)
        upper = text.upper()
        for suffix in ("-EQ", "-BE"):
            if upper.endswith(suffix):
                stripped = text[: -len(suffix)].strip()
                seg = {
                    "-EQ": ExchangeSegment.NSE,
                    "-BE": ExchangeSegment.BSE,
                }[suffix]
                return self._resolve_segmented(stripped, seg)

        # No prefix → try the default chain
        return self._resolve_default(text)

    def _resolve_default(self, text: str) -> ResolutionResult:
        """Resolve a symbol with no explicit segment prefix.

        Tries the segments in Trade_J's order: NSE_EQ, BSE_EQ, NSE_FNO,
        BSE_FNO, IDX_I, MCX, currency, and collects any matches.  If more
        than one segment matches, returns ``"ambiguous"``.
        """
        matches: list[DhanInstrumentDefinition] = []
        normalised = _csn_normalize(text)

        # 1) Compact F&O contracts must be resolved via the options/futures
        #    index (they don't live in the simple (wire::symbol) table).
        compact = _csn_parse(text)
        if compact is not None and compact.is_future:
            contracts = self._catalog.futures_contracts(compact.underlying)
            if contracts:
                today = date.today().isoformat()
                live = [c for c in contracts if c.expiry is None or c.expiry >= today]
                return ResolutionResult(
                    status="single" if len(live) == 1 else "ambiguous",
                    definition=live[0] if len(live) == 1 else None,
                    candidates=tuple(live),
                )
        if compact is not None and compact.is_option and compact.month:
            # Full option (e.g. ``NIFTY 30 JUN 25000 CE`` or ``NIFTY30JUN25000CE``)
            try:
                strike = int(float(compact.strike) * 100)
            except (TypeError, ValueError):
                strike = 0
            contracts = self._catalog.option_contracts(compact.underlying)
            if contracts:
                today = date.today()
                year_guesses = [today.year, today.year + 1]
                chosen: DhanInstrumentDefinition | None = None
                for year in year_guesses:
                    try:
                        expiry = date(year, _month_to_int(compact.month), compact.day)
                    except ValueError:
                        continue
                    iso = expiry.isoformat()
                    candidate = self._catalog.find_option_contract(
                        compact.underlying,
                        None,
                        iso,
                        strike,
                        compact.option_type,
                    )
                    if candidate is not None and candidate.expiry >= today.isoformat():
                        chosen = candidate
                        break
                if chosen is not None:
                    return ResolutionResult(status="single", definition=chosen)
        elif compact is not None and compact.is_option and not compact.month:
            # Bare option (e.g. ``NIFTY 25000 CE``) — find the nearest live one.
            try:
                strike = int(float(compact.strike) * 100)
            except (TypeError, ValueError):
                strike = 0
            contracts = self._catalog.option_contracts(compact.underlying)
            if contracts:
                today = date.today().isoformat()
                live = [
                    c
                    for c in contracts
                    if c.strike_price_paisa == strike
                    and c.option_type.upper() == compact.option_type.upper()
                    and (c.expiry is None or c.expiry >= today)
                ]
                if len(live) == 1:
                    return ResolutionResult(status="single", definition=live[0])
                if len(live) > 1:
                    return ResolutionResult(
                        status="ambiguous",
                        candidates=tuple(live),
                        reason=(
                            f"Multiple live {compact.underlying} {compact.strike} "
                            f"{compact.option_type} options found"
                        ),
                    )

        # 2) Bare "SYMBOL FUT" form (no date) → find the nearest live future.
        #    Examples: "RELIANCE FUT", "NIFTY FUT".
        upper = text.strip().upper()
        for suffix in (" FUT", " FUTURES"):
            if upper.endswith(suffix):
                underlying = upper[: -len(suffix)].strip()
                contracts = self._catalog.futures_contracts(underlying)
                if contracts:
                    today = date.today().isoformat()
                    live = [c for c in contracts if c.expiry is None or c.expiry >= today]
                    if len(live) == 1:
                        return ResolutionResult(status="single", definition=live[0])
                    if len(live) > 1:
                        return ResolutionResult(
                            status="ambiguous",
                            candidates=tuple(live),
                            reason=f"Multiple {underlying} futures contracts found",
                        )

        # 3) Walk the segment chain for plain equity / index lookups.
        for seg in (
            ExchangeSegment.NSE,
            ExchangeSegment.BSE,
            ExchangeSegment.NSE_FNO,
            ExchangeSegment.BSE_FNO,
            ExchangeSegment.IDX_I,
            ExchangeSegment.MCX,
            ExchangeSegment.NSE_CURRENCY,
            ExchangeSegment.BSE_CURRENCY,
        ):
            defn = self._catalog.get_definition(normalised, seg)
            if defn is not None:
                matches.append(defn)

        if len(matches) == 1:
            return ResolutionResult(status="single", definition=matches[0])
        if len(matches) > 1:
            return ResolutionResult(
                status="ambiguous",
                candidates=tuple(matches),
                reason=(
                    f"Multiple matches found for {text!r}: "
                    + ", ".join(f"{d.symbol} {d.exchange_segment.value}" for d in matches)
                    + ". Specify exchange."
                ),
            )
        return ResolutionResult(
            status="unknown",
            reason=f"No Dhan instrument found for symbol {text!r}",
        )

    def _resolve_segmented(self, text: str, segment: ExchangeSegment) -> ResolutionResult:
        normalised = _csn_normalize(text)
        # Try direct lookup first.
        defn = self._catalog.get_definition(normalised, segment)
        if defn is not None:
            return ResolutionResult(status="single", definition=defn)
        # Then try the segment's underlying-resolution chain so callers can
        # ask for "NSE_FNO:NIFTY" and still get the IDX_I index.
        for candidate in _lookup_segments(segment):
            if candidate == segment:
                continue  # already tried
            defn = self._catalog.get_definition(normalised, candidate)
            if defn is not None:
                return ResolutionResult(status="single", definition=defn)
        return ResolutionResult(
            status="unknown",
            reason=f"No Dhan instrument found for {text!r} on segment {segment.value}",
        )

    def require(self, raw: str) -> DhanInstrumentDefinition:
        """Resolve or raise :class:`ValueError` with a structured reason."""
        result = self.resolve(raw)
        if result.is_single and result.definition is not None:
            return result.definition
        if result.is_ambiguous:
            bullets = "\n  ".join(
                f"{d.symbol} {d.exchange_segment.value} (securityId={d.security_id})"
                for d in result.candidates
            )
            raise ValueError(
                f"Ambiguous symbol {raw!r}.\nMultiple matches found:\n  {bullets}\n"
                "Specify exchange (e.g. NSE:RELIANCE, BSE:RELIANCE)."
            )
        raise ValueError(result.reason or f"Unknown symbol {raw!r}")


# ─── Snapshot validation ─────────────────────────────────────────────────────


def validate_snapshot(
    path: Path,
    *,
    expected_columns: Iterable[str] = _REQUIRED_COLUMNS,
    require_unique_security_ids: bool = True,
) -> CatalogDiagnostics:
    """Validate a daily instrument snapshot and return a diagnostics report.

    Checks (audit §7):
    * File exists.
    * Record count > 0.
    * Required columns present.
    * Security IDs unique per ``(exchange_id, segment, security_id)``
      composite key (when ``require_unique_security_ids``).  Dhan reuses
      the same ``SEM_SMST_SECURITY_ID`` across different
      ``(exchange, segment)`` pairs, so uniqueness is enforced on the
      composite tuple, not on the bare SID.
    * Checksum computed.

    Raises :class:`SnapshotValidationError` on any hard failure.
    """
    if not path.exists():
        raise SnapshotValidationError(path, "file does not exist")
    if path.stat().st_size == 0:
        raise SnapshotValidationError(path, "file is empty")

    # Parse header to verify required columns AND locate the actual column
    # indices by name (SEM_EXM_EXCH_ID, SEM_SEGMENT, SEM_SMST_SECURITY_ID).
    # This is robust to future column reorderings — we never assume index 2.
    with open(path, encoding="utf-8", errors="replace") as fh:
        header_line = fh.readline()
    if not header_line:
        raise SnapshotValidationError(path, "missing CSV header")
    raw_header_cells = [c for c in header_line.strip().split(",") if c.strip()]
    headers_set = {_normalise_col(c) for c in raw_header_cells}
    missing = set(expected_columns) - headers_set
    if missing:
        raise SnapshotValidationError(path, f"missing required columns: {sorted(missing)}")

    header_index: dict[str, int] = {_normalise_col(c): i for i, c in enumerate(raw_header_cells)}
    exch_idx = header_index.get(_normalise_col(_COL_EXCHANGE_ID[0]))
    seg_idx = header_index.get(_normalise_col(_COL_SEGMENT[0]))
    sid_idx = header_index.get(_normalise_col(_COL_SECURITY_ID[0]))
    if exch_idx is None or seg_idx is None or sid_idx is None:
        raise SnapshotValidationError(
            path,
            "snapshot missing one of the required composite-key columns: "
            f"exchange={exch_idx is not None}, segment={seg_idx is not None}, "
            f"security_id={sid_idx is not None}",
        )

    # Stream the file to count records and check composite-key uniqueness.
    record_count = 0
    seen_composite: dict[tuple[str, str, str], int] = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh)
        next(reader)  # skip header
        for row in reader:
            if not any(c.strip() for c in row):
                continue
            record_count += 1
            try:
                exch = row[exch_idx].strip()
                seg = row[seg_idx].strip()
                sid = row[sid_idx].strip()
            except IndexError:
                continue
            if not sid:
                continue
            key = (exch, seg, sid)
            seen_composite[key] = seen_composite.get(key, 0) + 1

    if record_count == 0:
        raise SnapshotValidationError(path, "no data rows after header")

    duplicate_tuples = tuple(key for key, count in seen_composite.items() if count > 1)
    # Backward-compat: list unique SIDs that participate in any duplicate
    # tuple (this is a *different* list from duplicate_tuples: a SID may
    # legitimately appear in multiple (exch, seg) pairs, and the bare
    # duplicate-SID list is what older diagnostics reports expect).
    duplicate_sids = tuple(sorted({sid for (_exch, _seg, sid) in duplicate_tuples}))

    if require_unique_security_ids and duplicate_tuples:
        sample = sorted(duplicate_tuples)[:10]
        raise SnapshotValidationError(
            path,
            "duplicate (exchange, segment, security_id) tuples: "
            f"{sample}" + ("..." if len(duplicate_tuples) > 10 else ""),
        )

    return CatalogDiagnostics(
        record_count=record_count,
        by_security_id_size=len(seen_composite),
        duplicate_security_ids=duplicate_sids,
        duplicate_composite_keys=duplicate_tuples,
        checksum=_file_checksum(path),
    )


# ─── Private helpers ──────────────────────────────────────────────────────────


def _normalise_underlying(value: str) -> str:
    if not value:
        return ""
    normalised = value.strip().upper()
    first_space = normalised.find(" ")
    return normalised[:first_space] if first_space > 0 else normalised


def _strip_separators(value: str) -> str:
    """Remove spaces, hyphens, underscores; uppercase."""
    import re as _re

    return _re.sub(r"[\s\-_]+", "", value).upper()


def _month_to_int(month: str) -> int:
    return {
        "JAN": 1,
        "FEB": 2,
        "MAR": 3,
        "APR": 4,
        "MAY": 5,
        "JUN": 6,
        "JUL": 7,
        "AUG": 8,
        "SEP": 9,
        "OCT": 10,
        "NOV": 11,
        "DEC": 12,
    }.get(month.upper()[:3], 1)


def _extract_future_underlying(symbol: str) -> str:
    """Extract underlying from a futures trading symbol."""
    parsed = _csn_parse(symbol)
    if parsed is not None and not parsed.option:
        return parsed.underlying
    s = symbol.strip().upper()
    for suffix in ("FUTURES", "FUT"):
        if s.endswith(suffix):
            s = s[: -len(suffix)].rstrip()
    s = re.sub(r"^(.*?)(?:\d+|JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)+$", r"\1", s)
    return s.rstrip()


def _parse_date(value: str) -> str | None:
    if not value:
        return None
    v = value.strip()
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(v, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_decimal(value: str) -> Decimal | None:
    if not value or not value.strip():
        return None
    try:
        return Decimal(value.strip())
    except InvalidOperation:
        return None


def _parse_int(value: str, default: int = 0) -> int:
    if not value or not value.strip():
        return default
    try:
        return int(float(value.strip()))
    except (ValueError, TypeError):
        return default


def _parse_strike_paisa(value: str) -> int | None:
    """Parse a strike price in rupees to integer paisa — avoids float drift.

    Mirrors Trade_J's :class:`PriceMath.toPaisa`.
    """
    if not value or not value.strip():
        return None
    raw = value.strip()
    # Some Dhan rows have placeholder ``-0.01000`` for non-applicable strikes
    if raw.startswith("-"):
        # Negative placeholders mean "no strike" (e.g. futures / equity).
        return None
    try:
        dec = Decimal(raw)
    except InvalidOperation:
        return None
    return int((dec * 100).to_integral_value())


def _safe_wire(segment: ExchangeSegment) -> str | None:
    try:
        return to_wire_value(segment)
    except ValueError:
        return None


def _symbol_aliases(defn: DhanInstrumentDefinition) -> list[str]:
    """Return all symbol aliases to index for a definition.

    Includes the trading symbol, the canonical symbol, and Trade_J's
    ``aliasOptionCode`` compact + spaced option aliases.

    For futures and options, we intentionally **do not** add the bare
    ``underlying`` as a symbol alias — that would let a future
    ``RELIANCE-Jul2026-FUT`` show up when the user asks for ``RELIANCE``.
    The underlying is only used for the future/option sub-indexes.
    """
    aliases: set[str] = set()
    if defn.symbol:
        aliases.add(defn.symbol.upper())
        aliases.add(_strip_separators(defn.symbol))
    if defn.canonical_symbol:
        aliases.add(defn.canonical_symbol.upper())
    if defn.underlying and defn.is_index:
        aliases.add(defn.underlying.upper())
    # Trade_J aliasOptionCode — only useful for options, but inexpensive to compute.
    if defn.is_option and defn.expiry and defn.strike_price_paisa is not None:
        try:
            expiry_d = date.fromisoformat(defn.expiry)
        except ValueError:
            expiry_d = None
        if expiry_d is not None:
            try:
                expiry_d.strftime("%b")
            except ValueError:
                expiry_d = None
        if expiry_d is not None:
            compact = _csn_build_canonical(
                defn.underlying or defn.symbol,
                expiry_d,
                defn.strike_price_paisa,
                defn.option_type,
                is_option=True,
            )
            if compact:
                aliases.add(_strip_separators(compact))
                aliases.add(compact.upper())
    return sorted(aliases)


def _append_to(mapping: dict, key, value) -> None:
    if key not in mapping:
        mapping[key] = []
    if value not in mapping[key]:
        mapping[key].append(value)


def _lookup_segments(exchange_segment: ExchangeSegment) -> list[ExchangeSegment]:
    """Return the ordered list of segments to try when resolving an underlying.

    Mirrors Trade_J's DhanOptionsAdapter.lookupSegments():
    - NSE_FNO underlying: try IDX_I first (NIFTY, BANKNIFTY), then NSE_EQ, then NSE_FNO
    - BSE_FNO underlying: try IDX_I first (SENSEX), then BSE_EQ, then BSE_FNO
    - IDX_I direct: just IDX_I
    """
    if exchange_segment == ExchangeSegment.NSE_FNO:
        return [ExchangeSegment.IDX_I, ExchangeSegment.NSE, ExchangeSegment.NSE_FNO]
    if exchange_segment == ExchangeSegment.BSE_FNO:
        return [ExchangeSegment.IDX_I, ExchangeSegment.BSE, ExchangeSegment.BSE_FNO]
    if exchange_segment == ExchangeSegment.IDX_I:
        return [ExchangeSegment.IDX_I]
    return [exchange_segment]


def _candidate_derivative_segments(
    exchange_segment: ExchangeSegment,
) -> set[ExchangeSegment]:
    """Return which derivative segments are valid for a given underlying segment."""
    if exchange_segment in (
        ExchangeSegment.IDX_I,
        ExchangeSegment.NSE,
        ExchangeSegment.NSE_FNO,
    ):
        return {ExchangeSegment.NSE_FNO}
    if exchange_segment in (ExchangeSegment.BSE, ExchangeSegment.BSE_FNO):
        return {ExchangeSegment.BSE_FNO}
    if exchange_segment == ExchangeSegment.MCX:
        return {ExchangeSegment.MCX}
    return {exchange_segment}
