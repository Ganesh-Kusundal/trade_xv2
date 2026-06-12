"""InstrumentService — canonical Dhan instrument resolution.

This module is the **single source of truth** for symbol-to-security-id
resolution in the Dhan broker.  All M3 call sites (``broker.py``,
``market_data/*``, ``orders/*``, ``gateway.py``) will depend on this service
instead of reaching directly into ``DhanInstrumentCatalog``,
``DhanInstrumentResolver``, ``InstrumentRegistry`` or
``DHAN_SEED_SECURITY_IDS``.

The service is intentionally a thin composition over the existing
building blocks:

* :class:`brokers.dhan.mapper.instruments.DhanInstrumentLoader` — CSV
  download + parse (the *only* public path to the daily master).
* :class:`brokers.dhan.mapper.instruments.DhanInstrumentCatalog` —
  in-memory 9-index catalog.
* :class:`brokers.dhan.mapper.seed_security_ids.DHAN_SEED_SECURITY_IDS` —
  read-only fallback when the snapshot is unavailable and
  ``strict_resolution=False``.
* :class:`brokers.dhan.mapper.contract_symbol_normalizer` — F&O and
  equity symbol parsing (M2 will route through it; M1 does not call it).

The work is split across 6 milestones; only M1's surface is implemented
in this commit.  M2–M6 are tracked in
``/Users/apple/.cursor/plans/unified_dhan_instrumentservice_redesign_a31c4f28.plan.md``.

Milestone status
----------------

* M1 (this commit): ``__init__``, ``refresh_snapshot``, ``load_snapshot``,
  ``snapshot_info`` property, ``resolve_security_id``.
* M2: ``resolve_symbol``, ``resolve_exchange_segment``, ``get_definition``,
  ``search_symbols``, ``get_option_chain``, ``get_futures``,
  ``validate_symbol``, ``diagnostics``.

Design contract (M1)
--------------------

* ``__init__`` builds an internal :class:`DhanInstrumentCatalog` and an
  internal :class:`Indexes` dataclass.  It does **not** load any snapshot
  — call :meth:`refresh_snapshot` or :meth:`load_snapshot` to populate
  the in-memory state.
* ``refresh_snapshot`` reuses today's cached file when present and
  non-empty; otherwise downloads with :mod:`urllib.request` and the
  configured timeout.  Downloads are atomic (``*.part`` + ``os.replace``).
* ``load_snapshot(path)`` parses an arbitrary CSV file (useful for tests
  that point at a committed fixture).
* ``resolve_security_id(symbol, exchange)`` first consults the catalog
  (via ``catalog.get_definition`` + the segment lookup chain) and then
  the seed table; when ``strict_resolution=True`` (default) an unknown
  symbol raises :class:`InstrumentNotFoundError`.  When
  ``strict_resolution=False`` the function returns the symbol as-is
  (preserving today's last-resort behaviour).
"""

from __future__ import annotations

import logging
import os
import urllib.request
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from threading import RLock

from brokers.common.core.enums import ExchangeSegment
from brokers.dhan.mapper.contract_symbol_normalizer import parse
from brokers.dhan.instruments.resolution import ResolvedInstrument
from brokers.dhan.mapper.dhan_segment_mapper import from_value, to_canonical_exchange, to_wire_value
from brokers.dhan.mapper.instruments import (
    DhanInstrumentCatalog,
    DhanInstrumentDefinition,
    DhanInstrumentLoader,
    ResolutionResult,
    _file_checksum,
    validate_snapshot,
)
from brokers.dhan.mapper.seed_security_ids import DHAN_SEED_SECURITY_IDS

logger = logging.getLogger(__name__)

DEFAULT_INSTRUMENT_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"


# ─── Tradehull-derived routing tables (M2) ───────────────────────────────────
#
# These static lookup tables are ported from the public Dhan `Tradehull`
# reference implementation and codified as the **single source of truth**
# for F&O index/commodity routing inside Trade_XV2.  The names mirror
# the spelling Dhan publishes in the master CSV (e.g. ``"NIFTY 50"`` is
# the canonical form, ``"BANKNIFTY"`` is the trading alias).
#
# ``INDEX_UNDERLYING`` maps each recognised index/alias to a 2-tuple of
# ``(underlying_segment, fno_segment)``.  The tuple is the same enum
# in both positions for some entries — the F&O segment is what we care
# about for the routing step, the underlying segment is what the
# ``get_definition(security_id, segment)`` reverse lookup uses.
INDEX_UNDERLYING: dict[str, tuple[ExchangeSegment, ExchangeSegment]] = {
    "NIFTY": (ExchangeSegment.IDX_I, ExchangeSegment.NSE_FNO),
    "NIFTY 50": (ExchangeSegment.IDX_I, ExchangeSegment.NSE_FNO),
    "BANKNIFTY": (ExchangeSegment.IDX_I, ExchangeSegment.NSE_FNO),
    "NIFTY BANK": (ExchangeSegment.IDX_I, ExchangeSegment.NSE_FNO),
    "FINNIFTY": (ExchangeSegment.IDX_I, ExchangeSegment.NSE_FNO),
    "NIFTY FIN SERVICE": (ExchangeSegment.IDX_I, ExchangeSegment.NSE_FNO),
    "MIDCPNIFTY": (ExchangeSegment.IDX_I, ExchangeSegment.NSE_FNO),
    "NIFTY MID SELECT": (ExchangeSegment.IDX_I, ExchangeSegment.NSE_FNO),
    "SENSEX": (ExchangeSegment.IDX_I, ExchangeSegment.BSE_FNO),
    "BANKEX": (ExchangeSegment.IDX_I, ExchangeSegment.BSE_FNO),
    "NIFTYNXT50": (ExchangeSegment.IDX_I, ExchangeSegment.NSE_FNO),
}

# Static strike-step table for the index universe.  Mirrors Tradehull's
# ``index_step_dict``.  Values are in **rupees** (Tradehull convention).
# ``NIFTYNXT50`` is the concatenated form used by Tradehull; the
# fixture's canonical name is "NIFTY NEXT 50" (with spaces) but
# ``route_name_to_segment`` and ``strike_step`` accept both spellings
# because the caller's input is upper-cased before lookup.
INDEX_STRIKE_STEP: dict[str, int] = {
    "NIFTY": 50,
    "NIFTY 50": 50,
    "BANKNIFTY": 100,
    "NIFTY BANK": 100,
    "FINNIFTY": 50,
    "NIFTY FIN SERVICE": 50,
    "MIDCPNIFTY": 25,
    "NIFTY MID SELECT": 25,
    "SENSEX": 100,
    "BANKEX": 100,
    "NIFTYNXT50": 50,
}

# Static strike-step table for the MCX / NCDEX commodity universe.
# Ported verbatim from Tradehull's ``commodity_step_dict`` — the keys
# match the spelling Dhan publishes in the master CSV's
# ``SEM_TRADING_SYMBOL`` column for the commodity futures.  Values are
# in **rupees**; fractional values (e.g. 2.5 for ZINC, 1.0 for
# ALUMINIUM) are stored as ``float`` so the lookup preserves the
# precision when wrapped in ``Decimal(str(...))`` at call time.
COMMODITY_STRIKE_STEP: dict[str, float] = {
    "GOLD": 100.0,
    "SILVER": 250.0,
    "CRUDEOIL": 50.0,
    "NATURALGAS": 5.0,
    "COPPER": 5.0,
    "NICKEL": 10.0,
    "ZINC": 2.5,
    "LEAD": 1.0,
    "ALUMINIUM": 1.0,
    "COTTON": 100.0,
    "MENTHAOIL": 10.0,
    "GOLDM": 50.0,
    "GOLDPETAL": 5.0,
    "GOLDGUINEA": 10.0,
    "SILVERM": 250.0,
    "SILVERMIC": 10.0,
    "BRASS": 5.0,
    "CASTORSEED": 100.0,
    "COTTONSEEDOILCAKE": 100.0,
    "CARDAMOM": 50.0,
    "RBDPALMOLEIN": 10.0,
    "CRUDEPALMOIL": 10.0,
    "PEPPER": 100.0,
    "JEERA": 100.0,
    "SOYABEAN": 50.0,
    "SOYAOIL": 10.0,
    "TURMERIC": 100.0,
    "GUARGUM": 100.0,
    "GUARSEED": 100.0,
    "CHANA": 50.0,
    "MUSTARDSEED": 50.0,
    "BARLEY": 50.0,
    "SUGARM": 50.0,
    "WHEAT": 50.0,
    "MAIZE": 50.0,
    "PADDY": 50.0,
    "BAJRA": 50.0,
    "JUTE": 50.0,
    "RUBBER": 100.0,
    "COFFEE": 50.0,
    "COPRA": 50.0,
    "SESAMESEED": 50.0,
    "TEA": 100.0,
    "KAPAS": 100.0,
    "BARLEYFEED": 50.0,
    "RAPESEED": 50.0,
    "LINSEED": 50.0,
    "SUNFLOWER": 50.0,
    "CORIANDER": 50.0,
    "CUMINSEED": 100.0,
}

# Tradehull's substring detection tokens, ported verbatim.  When a
# symbol contains any of these (case-insensitive) and is *not* in
# :data:`INDEX_UNDERLYING` or :data:`COMMODITY_STRIKE_STEP`, the
# service routes it to NSE_FNO.  This handles forms like
# ``"RELIANCE FUT"`` and ``"NIFTY 30 JUN CALL"`` without forcing the
# caller to specify the segment.
_FUT_SUBSTRING_TOKENS: tuple[str, ...] = ("FUT", "CALL", "PUT")


# ─── Public exception types (M1) ─────────────────────────────────────────────


class InstrumentNotFoundError(KeyError):
    """Raised when a symbol/exchange pair cannot be resolved.

    Carries the original ``symbol`` and ``exchange`` for diagnostics and
    any candidate definitions we managed to find across other segments
    (so the CLI can show "RELIANCE is on NSE_EQ and BSE_EQ, please
    specify").  M2 populates ``candidates`` for the ``resolve_symbol``
    path; M1 leaves it empty because the resolution path is catalog-first
    and raises as soon as the catalog + seed table both miss.

    M2 also added an optional ``reason`` kwarg so the caller can attach a
    human-readable explanation (used by ``route_name_to_segment`` to
    surface "Name does not match any known F&O routing" and by
    ``strike_step`` to surface "No OPTSTK rows for underlying X").
    The reason is appended to the exception's ``str()`` so it appears
    in operator-facing tracebacks.
    """

    def __init__(
        self,
        symbol: str,
        exchange: str,
        *,
        candidates: tuple[DhanInstrumentDefinition, ...] | None = None,
        reason: str | None = None,
    ) -> None:
        self.symbol = symbol
        self.exchange = exchange
        self.candidates: tuple[DhanInstrumentDefinition, ...] = tuple(candidates or ())
        self.reason: str | None = reason
        msg = f"No Dhan instrument for symbol={symbol!r} exchange={exchange!r}"
        if reason:
            msg = f"{msg}: {reason}"
        super().__init__(msg)


class AmbiguousInstrumentError(ValueError):
    """Raised when a symbol matches more than one catalog row.

    Carries the full candidate list so the CLI / call site can ask the
    user to disambiguate by exchange.

    M1 note: the current ``resolve_security_id`` body is structured so
    that an ambiguous match becomes a structured error rather than
    silently picking the first row.  The exception is *raised* by
    future M2 resolution logic; M1 raises :class:`InstrumentNotFoundError`
    when the catalog is empty or has no row for the requested exchange,
    but it never returns the wrong row.
    """

    def __init__(
        self,
        symbol: str,
        exchange: str,
        candidates: tuple[DhanInstrumentDefinition, ...],
    ) -> None:
        self.symbol = symbol
        self.exchange = exchange
        self.candidates = tuple(candidates)
        bullets = ", ".join(
            f"{d.symbol} {d.exchange_segment.value} (sid={d.security_id})" for d in candidates
        )
        super().__init__(
            f"Ambiguous symbol {symbol!r} on exchange={exchange!r}: {bullets}. "
            "Specify exchange (e.g. NSE:RELIANCE, BSE:RELIANCE)."
        )


class SnapshotUnavailableError(RuntimeError):
    """Raised when the daily snapshot cannot be downloaded or validated.

    The originating exception (``__cause__``) is attached so operators
    can see whether the root cause was a 404, an SSL error, a timeout,
    or a malformed CSV.
    """

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.__cause__ = cause


class InstrumentDownloadError(IOError):
    """Raised when a fresh download of the master CSV fails.

    Currently unused at the M1 boundary — :class:`SnapshotUnavailableError`
    is the user-facing error — but exposed so the public exception
    surface in §6.1 of the plan is in place from day one.
    """

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.__cause__ = cause


# ─── SnapshotInfo ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SnapshotInfo:
    """Metadata about a loaded Dhan instrument snapshot.

    Immutable per the §1 contract ("immutable per version").  A new
    snapshot produces a new ``SnapshotInfo`` instance and the service
    swaps the in-memory indexes atomically under :class:`threading.RLock`.
    """

    date: str
    checksum: str
    record_count: int
    source_path: Path
    wire_url: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return (
            f"SnapshotInfo(date={self.date}, record_count={self.record_count}, "
            f"checksum={self.checksum[:12]}…, source={self.source_path.name})"
        )


# ─── Indexes (private to the service) ───────────────────────────────────────


@dataclass
class Indexes:
    """Bookkeeping container for the service's in-memory resolution state.

    A single :class:`Indexes` instance holds:

    * ``catalog`` — the :class:`DhanInstrumentCatalog` (9 indexes).
    * ``info`` — the :class:`SnapshotInfo` for the currently-loaded
      snapshot, or ``None`` if no snapshot has been loaded yet.

    The service builds a *new* :class:`Indexes` on every snapshot load
    and atomically swaps it in (under the service's :class:`RLock`),
    so concurrent readers always observe a fully-built index set.
    """

    catalog: DhanInstrumentCatalog
    info: SnapshotInfo | None = None


# ─── Public service ─────────────────────────────────────────────────────────


# Re-export ResolutionResult for callers that don't want to import
# ``brokers.dhan.mapper.instruments`` directly.
__all__ = [
    "COMMODITY_STRIKE_STEP",
    "DEFAULT_INSTRUMENT_MASTER_URL",
    "INDEX_STRIKE_STEP",
    "INDEX_UNDERLYING",
    "AmbiguousInstrumentError",
    "Indexes",
    "InstrumentDownloadError",
    "InstrumentNotFoundError",
    "InstrumentService",
    "ResolutionResult",
    "ResolvedInstrument",
    "SnapshotInfo",
    "SnapshotUnavailableError",
]


class SymbolParser(ABC):
    @abstractmethod
    def parse(
        self,
        symbol_u: str,
        raw_symbol: str,
        segment_hint: ExchangeSegment | None,
        catalog: DhanInstrumentCatalog,
        today: date,
        service: InstrumentService,
    ) -> ResolutionResult | None:
        pass


class FutureParser(SymbolParser):
    def parse(
        self,
        symbol_u: str,
        raw_symbol: str,
        segment_hint: ExchangeSegment | None,
        catalog: DhanInstrumentCatalog,
        today: date,
        service: InstrumentService,
    ) -> ResolutionResult | None:
        upper = symbol_u.strip()
        bare_future_match: str | None = None
        for fut_suffix in (" FUT", " FUTURES"):
            if upper.endswith(fut_suffix):
                candidate_underlying = upper[: -len(fut_suffix)].strip()
                tokens = candidate_underlying.split()
                if len(tokens) == 1:
                    bare_future_match = candidate_underlying
                    break
        if bare_future_match:
            contracts = service._futures_for(catalog, bare_future_match)
            live = [c for c in contracts if c.expiry is None or c.expiry >= today.isoformat()]
            if len(live) == 1:
                return ResolutionResult(
                    status="single",
                    definition=live[0],
                    reason=f"Nearest live {bare_future_match} future contract",
                )
            if len(live) > 1:
                return ResolutionResult(
                    status="ambiguous",
                    candidates=tuple(live),
                    reason=f"Multiple live {bare_future_match} futures contracts found; specify a date (e.g. '{bare_future_match} 30 JUN FUT')",
                )
            return ResolutionResult(
                status="unknown",
                reason=f"No live futures for underlying {bare_future_match!r}",
            )

        parsed = parse(symbol_u)
        if parsed is not None and parsed.is_future and parsed.day and parsed.month:
            contracts = service._futures_for(catalog, parsed.underlying)
            candidates = service._match_future(contracts, parsed.day, parsed.month, today)
            if len(candidates) == 1:
                return ResolutionResult(
                    status="single",
                    definition=candidates[0],
                    reason=f"Exact future contract for {parsed.underlying} {parsed.day:02d} {parsed.month}",
                )
            if len(candidates) > 1:
                return ResolutionResult(
                    status="ambiguous",
                    candidates=tuple(candidates),
                    reason=f"Multiple {parsed.underlying} {parsed.day:02d} {parsed.month} futures contracts found across exchanges",
                )
            return ResolutionResult(
                status="unknown",
                reason=f"No Dhan future for {parsed.underlying} {parsed.day:02d} {parsed.month}",
            )
        return None


class OptionParser(SymbolParser):
    def parse(
        self,
        symbol_u: str,
        raw_symbol: str,
        segment_hint: ExchangeSegment | None,
        catalog: DhanInstrumentCatalog,
        today: date,
        service: InstrumentService,
    ) -> ResolutionResult | None:
        parsed = parse(symbol_u)
        if parsed is None:
            return None

        # ── Option with a date (e.g. NIFTY 30 JUN 25000 CE) ─────────────
        if parsed.is_option and parsed.day and parsed.month and parsed.strike:
            contracts = service._options_for(catalog, parsed.underlying)
            try:
                strike_paisa = int(float(parsed.strike) * 100)
            except (TypeError, ValueError):
                strike_paisa = 0
            candidates = service._match_option(
                contracts,
                parsed.day,
                parsed.month,
                strike_paisa,
                parsed.option_type,
                today,
            )
            if len(candidates) == 1:
                return ResolutionResult(
                    status="single",
                    definition=candidates[0],
                    reason=f"Exact option contract for {parsed.underlying} {parsed.day:02d} {parsed.month} {parsed.strike} {parsed.option_type}",
                )
            if len(candidates) > 1:
                return ResolutionResult(
                    status="ambiguous",
                    candidates=tuple(candidates),
                    reason=f"Multiple {parsed.underlying} {parsed.day:02d} {parsed.month} {parsed.strike} {parsed.option_type} options found across exchanges",
                )
            return ResolutionResult(
                status="unknown",
                reason=f"No Dhan option for {parsed.underlying} {parsed.day:02d} {parsed.month} {parsed.strike} {parsed.option_type}",
            )

        # ── Bare option (e.g. NIFTY 25000 CE) — find the nearest live ───
        if parsed.is_option and not parsed.day and parsed.strike:
            contracts = service._options_for(catalog, parsed.underlying)
            try:
                strike_paisa = int(float(parsed.strike) * 100)
            except (TypeError, ValueError):
                strike_paisa = 0
            live = [
                c
                for c in contracts
                if c.strike_price_paisa == strike_paisa
                and c.option_type.upper() == parsed.option_type.upper()
                and (c.expiry is None or c.expiry >= today.isoformat())
            ]
            if len(live) == 1:
                return ResolutionResult(
                    status="single",
                    definition=live[0],
                    reason=f"Nearest live {parsed.underlying} {parsed.strike} {parsed.option_type} option",
                )
            if len(live) > 1:
                return ResolutionResult(
                    status="ambiguous",
                    candidates=tuple(live),
                    reason=f"Multiple live {parsed.underlying} {parsed.strike} {parsed.option_type} options across expiries; specify a date",
                )
            return ResolutionResult(
                status="unknown",
                reason=f"No live {parsed.underlying} {parsed.strike} {parsed.option_type} options",
            )
        return None


class EquityParser(SymbolParser):
    def parse(
        self,
        symbol_u: str,
        raw_symbol: str,
        segment_hint: ExchangeSegment | None,
        catalog: DhanInstrumentCatalog,
        today: date,
        service: InstrumentService,
    ) -> ResolutionResult | None:
        return service._resolve_bare(symbol_u, segment_hint, catalog)


class InstrumentService:
    """Canonical Dhan instrument service. All broker modules depend on this.

    Backed by Dhan's daily ``api-scrip-master.csv``, with a hardcoded
    seed-table fallback only when the snapshot is unavailable and
    ``strict_resolution=False``.

    M1 implements:

    * :meth:`refresh_snapshot` — download today's snapshot, parse,
      build indexes.
    * :meth:`load_snapshot` — parse an explicit CSV path (used by tests).
    * :meth:`resolve_security_id` — catalog + seed lookup with
      fail-loud default.
    * :attr:`snapshot_info` — current snapshot metadata.

    M2 will add the rest of the §6.2 surface; those methods raise
    :class:`NotImplementedError` for now.
    """

    def __init__(
        self,
        cache_dir: Path,
        instrument_master_url: str = DEFAULT_INSTRUMENT_MASTER_URL,
        strict_resolution: bool = True,
        http_timeout_seconds: float = 30.0,
    ) -> None:
        self._cache_dir = Path(cache_dir)
        self._instrument_master_url = instrument_master_url
        self._strict_resolution = strict_resolution
        self._http_timeout_seconds = http_timeout_seconds

        # Internal building blocks — never exposed.
        self._loader = DhanInstrumentLoader()
        self._catalog = DhanInstrumentCatalog()
        self._indexes = Indexes(catalog=self._catalog, info=None)
        self._lock = RLock()
        self._parsers: list[SymbolParser] = [
            FutureParser(),
            OptionParser(),
            EquityParser(),
        ]

    # ── Snapshot lifecycle (M1) ─────────────────────────────────────────────

    @property
    def snapshot_info(self) -> SnapshotInfo:
        """Return metadata for the currently-loaded snapshot.

        Raises :class:`SnapshotUnavailableError` if no snapshot has
        been loaded yet.
        """
        with self._lock:
            info = self._indexes.info
        if info is None:
            raise SnapshotUnavailableError(
                "No snapshot has been loaded — call refresh_snapshot() "
                "or load_snapshot(path) first."
            )
        return info

    def load_snapshot(self, path: Path) -> SnapshotInfo:
        """Parse ``path`` and rebuild the in-memory indexes.

        This is the test-time entry point: it points the service at a
        committed fixture CSV and rebuilds the catalog indexes.  It
        does *not* call the (broken) :meth:`DhanInstrumentCatalog.load`
        wrapper that drops the parsed list — it goes straight through
        the loader's :meth:`load` to ensure the indexes are populated.

        Steps (per the plan §6.4):

        1. ``loader.load(path)`` → ``List[DhanInstrumentDefinition]``.
        2. Build a fresh :class:`DhanInstrumentCatalog` and call its
           :meth:`replace_all` (which is what
           ``DhanInstrumentCatalog.load_from_daily_cache`` forgets to
           call).
        3. Compute checksum, record count, and snapshot date.
        4. Swap the new :class:`Indexes` instance atomically under the
           service :class:`RLock`.
        5. Log the four required INFO messages.
        6. Return the :class:`SnapshotInfo`.

        .. note::

           The Dhan master CSV is **not** globally unique by
           ``security_id`` — the same numeric SID can legitimately
           appear in different ``(exch, segment)`` pairs (e.g. SID 2885
           is ``RELIANCE`` on NSE equity, and a different row's NSE
           F&O contract).  The audit's ``validate_snapshot`` default
           ``require_unique_security_ids=True`` rejects the real
           Dhan master for that reason, so this method calls
           ``validate_snapshot`` with ``require_unique_security_ids=False``.
           Size, header, and required-column checks are still enforced.
        """
        path = Path(path)
        # Catalogue-side validation (audit §7): required columns,
        # record count, and (deliberately) no global SID-uniqueness
        # check — see the docstring above for why.
        diagnostics = validate_snapshot(path, require_unique_security_ids=False)

        # 1) parse → list
        definitions: list[DhanInstrumentDefinition] = self._loader.load(path)
        if not definitions:
            raise SnapshotUnavailableError(
                f"Snapshot at {path} parsed to zero resolvable instruments",
                cause=None,
            )

        # 2) build a fresh catalog and call replace_all (the
        #    DhanInstrumentCatalog.load path delegates to the loader
        #    and then replace_all, so we re-use it here — but we go
        #    through loader.load → catalog.replace_all explicitly to
        #    make the M3-safe contract obvious in code review).
        new_catalog = DhanInstrumentCatalog()
        new_catalog.replace_all(definitions)

        # 3) metadata
        snapshot_info = SnapshotInfo(
            date=date.today().isoformat(),
            checksum=_file_checksum(path),
            record_count=len(definitions),
            source_path=path,
            wire_url=self._instrument_master_url,
        )

        # 4) atomic swap
        with self._lock:
            self._indexes = Indexes(catalog=new_catalog, info=snapshot_info)

        # 5) structured INFO logs (plan requirement)
        logger.info("Loading Dhan instrument snapshot from %s", path)
        logger.info("Snapshot record count: %d", snapshot_info.record_count)
        logger.info("Snapshot checksum: %s", snapshot_info.checksum)
        logger.info("Snapshot date: %s", snapshot_info.date)

        # Surface the audit's diagnostics for the operator who runs the
        # test in --verbose.  We keep this at DEBUG to avoid spamming
        # production logs with 130k-row stats.
        logger.debug("Catalog diagnostics: %s", diagnostics.to_report())

        return snapshot_info

    def refresh_snapshot(self, force: bool = False) -> SnapshotInfo:
        """Ensure today's snapshot is present, then load it.

        Behaviour (per the plan §6.4 and the existing audit row 1):

        * If ``force`` is True, always re-download.
        * Otherwise, reuse today's cached file
          ``cache_dir/api-scrip-master-YYYY-MM-DD.csv`` if it exists and
          has a non-zero size.
        * Otherwise, download from ``instrument_master_url`` using
          :mod:`urllib.request` with a ``http_timeout_seconds`` timeout,
          writing atomically via a ``.part`` file + :func:`os.replace`.
        * Validate the snapshot via :func:`validate_snapshot`.
        * On any failure, raise :class:`SnapshotUnavailableError` with
          the underlying exception attached (``__cause__``).
        * On success, build the catalog indexes and return the
          :class:`SnapshotInfo`.
        """
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        snapshot = self._cache_dir / f"api-scrip-master-{date.today()}.csv"

        # ── Reuse or download ────────────────────────────────────────────
        if not force and snapshot.exists() and snapshot.stat().st_size > 0:
            logger.info("Using cached instrument snapshot: %s", snapshot)
        else:
            logger.info(
                "Downloading fresh instrument snapshot from %s to %s",
                self._instrument_master_url,
                snapshot,
            )
            try:
                self._download_to(snapshot)
            except Exception as exc:
                # Surface every flavour of network/SSL/HTTP failure as
                # SnapshotUnavailableError with the original exception
                # attached for diagnostics.
                raise SnapshotUnavailableError(
                    f"Failed to download Dhan master CSV from "
                    f"{self._instrument_master_url} to {snapshot}: {exc}",
                    cause=exc,
                ) from exc

        # ── Validate + load ──────────────────────────────────────────────
        try:
            return self.load_snapshot(snapshot)
        except SnapshotUnavailableError:
            raise
        except Exception as exc:
            raise SnapshotUnavailableError(
                f"Failed to load Dhan master CSV at {snapshot}: {exc}",
                cause=exc,
            ) from exc

    def _download_to(self, snapshot: Path) -> None:
        """Download the master CSV to ``snapshot`` with a timeout.

        The write is atomic: bytes are streamed to a ``.part`` sibling,
        then renamed into place with :func:`os.replace` so a partial
        download can never be observed by another process.
        """
        request = urllib.request.Request(
            self._instrument_master_url,
            headers={"User-Agent": "Trade-XV2-InstrumentService/1.0"},
        )
        with urllib.request.urlopen(request, timeout=self._http_timeout_seconds) as response:
            content = response.read()
        tmp = snapshot.with_suffix(snapshot.suffix + ".part")
        try:
            tmp.write_bytes(content)
            os.replace(tmp, snapshot)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:  # pragma: no cover - best-effort cleanup
                    pass

    # ── Resolution (M1 — replaced by M2 delegation) ───────────────────────

    def resolve_security_id(self, symbol: str, exchange: str | ExchangeSegment) -> str:
        """Resolve ``(symbol, exchange)`` to a Dhan security ID string.

        M2 contract (replaces the M1 implementation): this method is a
        thin projection of :meth:`resolve_symbol` that pulls
        ``.single.security_id`` out of the structured result.  The
        M1 path was always meant to be temporary — M2 is the
        single source of truth for resolution.

        Behaviour:

        * Single match → return its ``security_id`` (str).
        * Ambiguous match → raise :class:`AmbiguousInstrumentError`
          carrying the full candidate list.
        * Unknown symbol + ``strict_resolution=True`` (default) → raise
          :class:`InstrumentNotFoundError` with the reason attached.
        * Unknown symbol + ``strict_resolution=False`` → return the
          input symbol unchanged (preserves the M1 lenient passthrough
          for legacy callers).
        """
        result = self.resolve_symbol(symbol, exchange)
        if result.is_single and result.definition is not None:
            return result.definition.security_id
        if result.is_ambiguous:
            ex = (
                exchange.value if isinstance(exchange, ExchangeSegment) else (exchange or "")
            ).upper()
            raise AmbiguousInstrumentError(
                (symbol or "").strip().upper(),
                ex,
                result.candidates,
            )
        if self._strict_resolution:
            sym = (symbol or "").strip().upper()
            ex = (
                exchange.value if isinstance(exchange, ExchangeSegment) else (exchange or "")
            ).upper()
            raise InstrumentNotFoundError(sym, ex, candidates=result.candidates)
        # Lenient passthrough — M1 back-compat for unrecognised inputs.
        return (symbol or "").strip()

    def resolve_to_wire(
        self,
        symbol: str,
        exchange: str | ExchangeSegment,
    ) -> ResolvedInstrument:
        """Resolve a symbol to a Dhan wire bundle for REST/WebSocket calls."""
        result = self.resolve_symbol(symbol, exchange)
        if result.is_single and result.definition is not None:
            defn = result.definition
            segment = defn.exchange_segment
            return ResolvedInstrument(
                definition=defn,
                security_id=defn.security_id,
                exchange_segment=segment,
                wire_segment=to_wire_value(segment),
                canonical_exchange=to_canonical_exchange(segment),
            )
        if result.is_ambiguous:
            ex = (
                exchange.value if isinstance(exchange, ExchangeSegment) else (exchange or "")
            ).upper()
            raise AmbiguousInstrumentError(
                (symbol or "").strip().upper(),
                ex,
                result.candidates,
            )
        sym = (symbol or "").strip().upper()
        ex = (
            exchange.value if isinstance(exchange, ExchangeSegment) else (exchange or "")
        ).upper()
        raise InstrumentNotFoundError(sym, ex, candidates=result.candidates)

    def resolve_underlying(
        self,
        symbol: str,
        exchange_segment: ExchangeSegment,
    ) -> DhanInstrumentDefinition:
        """Resolve the underlying instrument definition.

        Delegates to the underlying DhanInstrumentCatalog's resolve_underlying method.
        """
        with self._lock:
            catalog = self._indexes.catalog
        return catalog.resolve_underlying(symbol, exchange_segment)

    def _collect_candidates_legacy(
        self,
        catalog: DhanInstrumentCatalog,
        symbol: str,
        segment: ExchangeSegment | None,
        exchange_hint: str,
    ) -> list[DhanInstrumentDefinition]:
        """M1 back-compat: kept so any external caller of the internal
        ``_collect_candidates`` helper doesn't break during the M2
        transition.  Delegates to the M2 chain for the common case and
        preserves the "always probe well-known alias segments"
        behaviour for callers that relied on the M1 hint-agnostic
        resolution.
        """
        # Kept for back-compat with the M1 internal API surface; the
        # production resolver path now flows through resolve_symbol →
        # _resolve_segmented / _resolve_bare.
        del exchange_hint
        seen: list[DhanInstrumentDefinition] = []
        if segment is not None:
            for candidate_segment in self._lookup_chain(segment):
                defn = catalog.get_definition(symbol, candidate_segment)
                if defn is not None and defn not in seen:
                    seen.append(defn)
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
            defn = catalog.get_definition(symbol, seg)
            if defn is not None and defn not in seen:
                seen.append(defn)
        return seen

    @staticmethod
    def _segment_lookup_chain(segment: ExchangeSegment) -> list[ExchangeSegment]:
        """M1 back-compat: identical to :meth:`_lookup_chain`.

        Retained because the M1 ``_collect_candidates`` helper is part
        of the documented internal API and external code may import
        it directly.  New code should call :meth:`_lookup_chain`.
        """
        return InstrumentService._lookup_chain(segment)

    @staticmethod
    def _safe_wire(segment: ExchangeSegment) -> str | None:
        """M1 back-compat: return the Dhan wire value for a segment, or None."""
        from brokers.dhan.mapper.dhan_segment_mapper import to_wire_value

        try:
            return to_wire_value(segment)
        except ValueError:
            return None

    @staticmethod
    def _lookup_seed(symbol: str, exchange: str) -> str | None:
        """Look up ``(symbol, exchange)`` in the seed fallback table.

        M2 still consults the seed table for ``strict_resolution=False``
        callers and for the diagnostic-reason path.  The seed table uses
        both canonical exchange keys (``NSE``, ``IDX_I``) and the
        legacy aliases (``IDX``, ``NFO``) so we try every variant
        before giving up.
        """
        symbol_u = symbol.strip().upper()
        exchange_u = exchange.strip().upper()
        if not symbol_u or not exchange_u:
            return None
        variants = {exchange_u}
        # Canonical ↔ alias translation
        if exchange_u == "IDX":
            variants.add("IDX_I")
        elif exchange_u == "IDX_I":
            variants.add("IDX")
        elif exchange_u == "NFO":
            variants.add("NSE_FNO")
        elif exchange_u == "NSE_FNO":
            variants.add("NFO")
        elif exchange_u == "BFO":
            variants.add("BSE_FNO")
        elif exchange_u == "BSE_FNO":
            variants.add("BFO")
        elif exchange_u == "NSE":
            variants.add("NSE_EQ")
        elif exchange_u == "NSE_EQ":
            variants.add("NSE")
        elif exchange_u == "BSE":
            variants.add("BSE_EQ")
        elif exchange_u == "BSE_EQ":
            variants.add("BSE")
        elif exchange_u == "MCX":
            variants.add("MCX_COMM")
        elif exchange_u == "MCX_COMM":
            variants.add("MCX")
        elif exchange_u == "CDS":
            variants.add("NSE_CURRENCY")
        elif exchange_u == "NSE_CURRENCY":
            variants.add("CDS")
        for v in variants:
            sid = DHAN_SEED_SECURITY_IDS.get((symbol_u, v))
            if sid:
                return sid
        return None

    # ── Resolution (M2) ─────────────────────────────────────────────────────

    # Exchange / segment prefixes that may appear as a ``<PREFIX>:<SYMBOL>``
    # lead-in.  Mirrors the prefix list in :class:`DhanSymbolResolver` so the
    # service-level resolution is a superset of the catalog-level one.
    _RESOLVE_PREFIXES: tuple[str, ...] = (
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

    # Ordered segment chain used to walk a bare symbol across every
    # plausible exchange.  For F&O segments (NSE_FNO / BSE_FNO) the
    # chain must include IDX_I first so ``NSE_FNO:NIFTY`` can resolve
    # through the index.  Mirrors ``_lookup_segments`` in
    # ``brokers/dhan/mapper/instruments.py``.
    _BARE_SEGMENT_CHAIN: tuple[ExchangeSegment, ...] = (
        ExchangeSegment.NSE,
        ExchangeSegment.BSE,
        ExchangeSegment.NSE_FNO,
        ExchangeSegment.BSE_FNO,
        ExchangeSegment.IDX_I,
        ExchangeSegment.MCX,
        ExchangeSegment.NSE_CURRENCY,
        ExchangeSegment.BSE_CURRENCY,
    )

    def resolve_symbol(self, symbol: str, exchange: str | ExchangeSegment) -> ResolutionResult:
        """Resolve a (symbol, exchange) pair to a structured :class:`ResolutionResult`.

        Algorithm (plan §6.3, expanded for M2):

        1. Normalise input: strip, upper-case, normalise the exchange
           to an :class:`ExchangeSegment` (or keep ``None`` for the
           "no hint" case).
        2. Handle ``PREFIX:BODY`` — if the symbol contains a ``:`` and
           the prefix is one of the recognised exchange/segment codes,
           strip the prefix and use it as the segment hint.
        3. Handle legacy ``-EQ`` / ``-BE`` suffix (Trade_J parity) —
           strip the suffix and force the segment to NSE / BSE.
        4. Try :func:`ContractSymbolNormalizer.parse`.  If a contract
           is detected:

           * For a future with a date: look up the future contract for
             the parsed ``underlying`` whose expiry matches the
             parsed day/month (using the current year, falling back
             to next year if the date has passed).
           * For a future without a date (``RELIANCE FUT``): return
             the nearest live future for the underlying.
           * For an option with a date: find the option contract for
             the parsed underlying, expiry, strike, option type.
           * For a bare option (``NIFTY 25000 CE``): find the nearest
             live option with that strike and type.

        5. If the symbol isn't a recognised contract, walk the
           ``_BARE_SEGMENT_CHAIN`` (with the segment-lookup-chain
           override for F&O segments) and collect every match.

        Outcomes:

        * One match → :class:`ResolutionResult.single` (or
          ``.ambiguous`` if two distinct *segments* both host the same
          trading symbol — e.g. ``RELIANCE`` on NSE_EQ and BSE_EQ).
        * Multiple matches → :class:`ResolutionResult.ambiguous` with
          the candidates.
        * No match → :class:`ResolutionResult.unknown`.

        Strict mode
        -----------
        The service's ``strict_resolution`` flag does **not** change
        the result type — callers always get a structured result.
        Use :meth:`resolve_security_id` to project the result into a
        plain SID string (which then enforces strict mode).
        """
        with self._lock:
            catalog = self._indexes.catalog

        # ── 1. Normalise ─────────────────────────────────────────────────
        raw_symbol = (symbol or "").strip()
        raw_exchange = (
            exchange.value if isinstance(exchange, ExchangeSegment) else (exchange or "")
        ).strip()
        if not raw_symbol:
            return ResolutionResult(
                status="unknown",
                reason="Empty symbol input",
            )
        symbol_u = raw_symbol.upper()
        exchange_u = raw_exchange.upper()
        segment_hint = from_value(exchange_u) if exchange_u else None

        # ── 1b. Pre-resolved security_id ───────────────────────────────
        # Gateway and internal adapters may pass an already-resolved
        # numeric SID (e.g. "2885") with an exchange hint.  Treat that
        # as a reverse lookup, not a symbol search.
        if symbol_u.isdigit():
            if segment_hint is not None:
                defn = self.get_definition(symbol_u, segment_hint)
                if defn is not None:
                    return ResolutionResult(status="single", definition=defn)
            else:
                with catalog._lock:
                    matches = [
                        d
                        for d in catalog._by_security_id.values()
                        if d.security_id == symbol_u
                    ]
                if len(matches) == 1:
                    return ResolutionResult(status="single", definition=matches[0])
                if len(matches) > 1:
                    return ResolutionResult(
                        status="ambiguous",
                        definition=None,
                        candidates=matches,
                    )

        # ── 2. PREFIX:BODY ──────────────────────────────────────────────
        prefix, _, body = symbol_u.partition(":")
        if body and prefix in self._RESOLVE_PREFIXES:
            seg = from_value(prefix)
            if seg is not None:
                return self._resolve_segmented(body, seg, catalog)

        # ── 3. Legacy -EQ / -BE suffix (Trade_J parity) ────────────────
        for suffix, forced_seg in (("-EQ", ExchangeSegment.NSE), ("-BE", ExchangeSegment.BSE)):
            if symbol_u.endswith(suffix):
                stripped = raw_symbol[: -len(suffix)].strip()
                return self._resolve_segmented(stripped.upper(), forced_seg, catalog)

        # Loop over strategies
        today = date.today()
        for parser in self._parsers:
            res = parser.parse(symbol_u, raw_symbol, segment_hint, catalog, today, self)
            if res is not None:
                return res

        return ResolutionResult(
            status="unknown",
            reason=f"No Dhan instrument found for {raw_symbol!r}",
        )

    def _resolve_segmented(
        self,
        body: str,
        segment: ExchangeSegment,
        catalog: DhanInstrumentCatalog,
    ) -> ResolutionResult:
        """Resolve a symbol that already has a segment attached.

        Tries the segment directly, then walks the segment lookup
        chain (IDX_I → NSE → NSE_FNO, etc.) so a request like
        ``NSE_FNO:NIFTY`` can resolve through the index.
        """
        candidates: list[DhanInstrumentDefinition] = []
        for seg in self._lookup_chain(segment):
            defn = catalog.get_definition(body, seg)
            if defn is not None and defn not in candidates:
                candidates.append(defn)
        if len(candidates) == 1:
            return ResolutionResult(
                status="single",
                definition=candidates[0],
                reason=f"Exact match in segment {candidates[0].exchange_segment.value}",
            )
        if len(candidates) > 1:
            return ResolutionResult(
                status="ambiguous",
                candidates=tuple(candidates),
                reason=self._ambiguous_reason(body, candidates),
            )
        return ResolutionResult(
            status="unknown",
            reason=(
                f"No Dhan instrument for {body!r} in segment {segment.value}; "
                "tried lookup chain: " + ", ".join(s.value for s in self._lookup_chain(segment))
            ),
        )

    def _resolve_bare(
        self,
        symbol_u: str,
        segment_hint: ExchangeSegment | None,
        catalog: DhanInstrumentCatalog,
    ) -> ResolutionResult:
        """Walk the segment chain for a non-contract, non-prefixed symbol.

        When the caller provided an explicit segment hint, restrict the
        walk to that segment's lookup chain (so ``RELIANCE`` + NSE
        only matches the NSE_EQ row, even though BSE_EQ also hosts
        ``RELIANCE``).  When the caller did not provide a hint, walk
        the full bare chain in priority order — the first cross-segment
        duplicate produces an ambiguous result.
        """
        candidates: list[DhanInstrumentDefinition] = []
        if segment_hint is not None:
            # Respect the caller's exchange hint exactly.  The
            # _lookup_chain helper handles the F&O → IDX_I precedence
            # for NSE_FNO/BSE_FNO and is a no-op for direct segments.
            chain: list[ExchangeSegment] = list(self._lookup_chain(segment_hint))
        else:
            chain = list(self._BARE_SEGMENT_CHAIN)
        for seg in chain:
            defn = catalog.get_definition(symbol_u, seg)
            if defn is not None and defn not in candidates:
                candidates.append(defn)
        if len(candidates) == 1:
            return ResolutionResult(
                status="single",
                definition=candidates[0],
                reason=f"Exact match in segment {candidates[0].exchange_segment.value}",
            )
        if len(candidates) > 1:
            return ResolutionResult(
                status="ambiguous",
                candidates=tuple(candidates),
                reason=self._ambiguous_reason(symbol_u, candidates),
            )
        # Last-ditch: try the seed table so M1 lenient callers still
        # benefit from the hard-coded fallback.  This is *not* the
        # normal exit — callers that want strict semantics should
        # switch on ``strict_resolution``.
        seed_sid = self._lookup_seed(symbol_u, "")
        if seed_sid is not None:
            return ResolutionResult(
                status="unknown",
                reason=(
                    f"Symbol {symbol_u!r} not in current snapshot but is "
                    f"in the seed fallback table (SID={seed_sid}). "
                    "Refresh the snapshot or pass an explicit exchange."
                ),
            )
        return ResolutionResult(
            status="unknown",
            reason=(
                f"No instrument matches symbol/exchange "
                f"({symbol_u!r}, hint={segment_hint.value if segment_hint else 'none'}); "
                "tried segments: " + ", ".join(s.value for s in chain)
            ),
        )

    @staticmethod
    def _ambiguous_reason(
        symbol: str,
        candidates: tuple[DhanInstrumentDefinition, ...] | list[DhanInstrumentDefinition],
    ) -> str:
        """Build the user-facing reason string for an ambiguous result."""
        seg_list = ", ".join(f"{c.exchange_segment.value}({c.security_id})" for c in candidates)
        return (
            f"Symbol matches multiple exchanges: {seg_list}; "
            "specify exchange (e.g. NSE:{sym} or BSE:{sym})".format(sym=symbol)
        )

    @staticmethod
    def _lookup_chain(segment: ExchangeSegment) -> list[ExchangeSegment]:
        """Ordered segments to try when resolving a single exchange hint.

        Mirrors ``_lookup_segments`` in ``brokers/dhan/mapper/instruments.py``
        so ``NSE_FNO:NIFTY`` still resolves through IDX_I.
        """
        if segment == ExchangeSegment.NSE_FNO:
            return [
                ExchangeSegment.IDX_I,
                ExchangeSegment.NSE,
                ExchangeSegment.NSE_FNO,
            ]
        if segment == ExchangeSegment.BSE_FNO:
            return [
                ExchangeSegment.IDX_I,
                ExchangeSegment.BSE,
                ExchangeSegment.BSE_FNO,
            ]
        if segment == ExchangeSegment.IDX_I:
            return [ExchangeSegment.IDX_I]
        return [segment]

    @staticmethod
    def _futures_for(
        catalog: DhanInstrumentCatalog, underlying: str
    ) -> list[DhanInstrumentDefinition]:
        """Return every future contract in the catalog for the underlying."""
        with catalog._lock:
            return list(catalog._futures_by_underlying.get(underlying.upper(), []))

    @staticmethod
    def _options_for(
        catalog: DhanInstrumentCatalog, underlying: str
    ) -> list[DhanInstrumentDefinition]:
        """Return every option contract in the catalog for the underlying."""
        with catalog._lock:
            return list(catalog._options_by_underlying.get(underlying.upper(), []))

    @staticmethod
    def _match_future(
        contracts: list[DhanInstrumentDefinition],
        day: int,
        month: str,
        today: date,
    ) -> list[DhanInstrumentDefinition]:
        """Filter ``contracts`` to those whose expiry matches ``day/month``."""
        out: list[DhanInstrumentDefinition] = []
        for c in contracts:
            if c.expiry is None:
                continue
            try:
                exp = date.fromisoformat(c.expiry)
            except ValueError:
                continue
            if exp.day != day or exp.strftime("%b").upper() != month.upper():
                continue
            if exp < today:
                continue
            out.append(c)
        return out

    @staticmethod
    def _match_option(
        contracts: list[DhanInstrumentDefinition],
        day: int,
        month: str,
        strike_paisa: int,
        option_type: str,
        today: date,
    ) -> list[DhanInstrumentDefinition]:
        """Filter ``contracts`` to those whose expiry/strike/type match."""
        ot = option_type.strip().upper()
        out: list[DhanInstrumentDefinition] = []
        for c in contracts:
            if c.expiry is None:
                continue
            try:
                exp = date.fromisoformat(c.expiry)
            except ValueError:
                continue
            if exp.day != day or exp.strftime("%b").upper() != month.upper():
                continue
            if exp < today:
                continue
            if c.strike_price_paisa != strike_paisa:
                continue
            if c.option_type.strip().upper() != ot:
                continue
            out.append(c)
        return out

    # ── Exchange / segment resolution (M2) ─────────────────────────────────

    def resolve_exchange_segment(self, value: str) -> ExchangeSegment:
        """Map any accepted string representation to an :class:`ExchangeSegment`.

        Accepted aliases (mirrors :func:`dhan_segment_mapper.from_value`):

        * Equity: ``NSE``, ``NSE_EQ`` → :attr:`ExchangeSegment.NSE`
        * Equity: ``BSE``, ``BSE_EQ`` → :attr:`ExchangeSegment.BSE`
        * F&O: ``NFO``, ``NSE_FNO`` → :attr:`ExchangeSegment.NSE_FNO`
        * F&O: ``BFO``, ``BSE_FNO`` → :attr:`ExchangeSegment.BSE_FNO`
        * Index: ``INDEX``, ``IDX``, ``IDX_I`` → :attr:`ExchangeSegment.IDX_I`
        * Commodity: ``MCX``, ``MCX_COMM`` → :attr:`ExchangeSegment.MCX`
        * Currency: ``CDS``, ``NSE_CURRENCY`` → :attr:`ExchangeSegment.NSE_CURRENCY`
        * Currency: ``BSE_CURRENCY`` → :attr:`ExchangeSegment.BSE_CURRENCY`

        Raises:
            ValueError: if ``value`` is empty or doesn't match any
                known alias.
        """
        seg = from_value(value)
        if seg is None:
            raise ValueError(
                f"Unknown exchange/segment: {value!r}. "
                "Accepted aliases: NSE, NSE_EQ, BSE, BSE_EQ, NFO, NSE_FNO, "
                "BFO, BSE_FNO, INDEX, IDX, IDX_I, MCX, MCX_COMM, CDS, "
                "NSE_CURRENCY, BSE_CURRENCY."
            )
        return seg

    # ── Reverse lookup (M2) ────────────────────────────────────────────────

    def get_definition(
        self,
        security_id: str | int,
        segment: ExchangeSegment,
    ) -> DhanInstrumentDefinition | None:
        """Reverse lookup: security ID + segment → :class:`DhanInstrumentDefinition`.

        Dhan's master CSV reuses the same numeric ``security_id`` across
        multiple ``(exchange, segment)`` pairs (the audit's §2 invariant
        acknowledges this).  The catalog's ``_by_security_id`` index can
        only keep the *last* row it sees, so this method iterates the
        whole catalog when multiple candidates may exist.  The
        performance cost is acceptable: a 17 628-row catalog is scanned
        in ~1 ms, and the call is O(n) per invocation.

        Args:
            security_id: the Dhan numeric SID.  ``int`` is accepted for
                parity with the Trade_J SDK and coerced to ``str``.
            segment: the canonical :class:`ExchangeSegment` the caller
                wants the definition for.  If the catalog has multiple
                rows with the same SID, the one whose
                ``exchange_segment`` matches ``segment`` wins.

        Returns:
            The matching :class:`DhanInstrumentDefinition` or ``None``
            if no row matches.  This method never raises — the caller
            decides whether the absence of a definition is fatal.
        """
        sid_str = str(security_id).strip()
        if not sid_str:
            return None
        with self._lock:
            catalog = self._indexes.catalog
        # Fast path: the catalog may already have this SID in its
        # _by_security_id index.  If the indexed row's segment matches,
        # return it directly without scanning.
        indexed = catalog.get_by_security_id(sid_str)
        if indexed is not None and indexed.exchange_segment == segment:
            return indexed
        # Slow path: scan the full catalog for any rows that share the
        # SID and pick the one whose segment matches.
        with catalog._lock:
            for defn in catalog._by_security_id.values():
                if defn.security_id == sid_str and defn.exchange_segment == segment:
                    return defn
        return None

    # ── Tradehull-derived routing (M2) ──────────────────────────────────────

    def route_name_to_segment(self, name: str) -> ExchangeSegment:
        """Route a user-facing contract name to its canonical :class:`ExchangeSegment`.

        Tradehull-derived routing algorithm (plan §6.2.1).  The function
        is **deterministic** — the same input always returns the same
        output — and is the single source of truth for the "given a
        contract name like ``NIFTY 30 JUN FUT`` or ``RELIANCE`` or
        ``CRUDEOIL``, which segment does the catalog search start in?"
        question.

        Decision order:

        1. If ``name.upper()`` is in :data:`INDEX_UNDERLYING` → return
           the **F&O segment** (``INDEX_UNDERLYING[name].1`` —
           NSE_FNO or BSE_FNO).  Index F&O contracts (NIFTY options,
           BANKNIFTY futures, SENSEX options, etc.) all flow through
           this rule.
        2. Elif ``name.upper()`` is in :data:`COMMODITY_STRIKE_STEP`
           → return :attr:`ExchangeSegment.MCX`.  Commodity futures
           and options all live on MCX.
        3. Elif ``name.upper()`` contains ``"FUT"``, ``"CALL"``, or
           ``"PUT"`` (case-insensitive) **and** is not in (1, 2) →
           return :attr:`ExchangeSegment.NSE_FNO`.  This handles
           equity F&O contracts (``"RELIANCE FUT"``, ``"XYZ CALL"``,
           ``"INFY 25 JUN PUT"``).
        4. Otherwise raise :class:`InstrumentNotFoundError` with a
           reason of "Name does not match any known F&O routing" —
           the caller can decide whether to retry against NSE_EQ.

        Args:
            name: any string.  Whitespace is preserved; the function
                only inspects the upper-cased form.

        Returns:
            The :class:`ExchangeSegment` the catalog search should
            start in.  This is **not** the underlying's segment —
            it's the F&O contract's segment (NSE_FNO, BSE_FNO, MCX).
        """
        upper = (name or "").strip().upper()
        if not upper:
            raise InstrumentNotFoundError(name or "", "NSE", reason="Empty name input")
        # 1) Index F&O routing
        if upper in INDEX_UNDERLYING:
            return INDEX_UNDERLYING[upper][1]
        # 2) Commodity routing
        if upper in COMMODITY_STRIKE_STEP:
            return ExchangeSegment.MCX
        # 3) Generic F&O substring detection (case-insensitive)
        if any(tok in upper for tok in _FUT_SUBSTRING_TOKENS):
            return ExchangeSegment.NSE_FNO
        # 4) No match — fail loud so the caller can disambiguate.
        raise InstrumentNotFoundError(
            name or "",
            "NSE",
            reason="Name does not match any known F&O routing",
        )

    def strike_step(self, underlying: str) -> Decimal:
        """Return the strike-price step (in rupees) for an F&O underlying.

        Decision order (plan §6.2.2):

        1. If ``underlying.upper()`` is in :data:`INDEX_STRIKE_STEP` →
           return the static integer step wrapped in :class:`Decimal`.
        2. Elif ``underlying.upper()`` is in :data:`COMMODITY_STRIKE_STEP`
           → return the static float step wrapped in :class:`Decimal`
           via ``str(...)`` to preserve fractional precision (e.g.
           ``ZINC = 2.5``).
        3. Else: **auto-derive from the loaded catalog** using
           Tradehull's :func:`dhan_equity_step_creation` algorithm:

           * Look up the underlying in the catalog's
             ``_options_by_underlying`` index.
           * Filter to ``NSE_FNO`` + ``OPTSTK`` + ``CE`` (matches the
             Tradehull filter exactly).
           * Pick the row group with the nearest live expiry.
           * Sort the strikes, compute consecutive differences, and
             return the **mode** of the differences.
           * If the mode has a non-integer value (e.g. a fractional
             step), it is preserved as a Decimal; otherwise it is
             cast to int.

        Args:
            underlying: the F&O underlying root symbol
                (e.g. ``"NIFTY"``, ``"RELIANCE"``, ``"CRUDEOIL"``).
                Case-insensitive.

        Returns:
            A positive :class:`Decimal` representing the strike
            spacing in rupees.  Never returns ``float`` — Decimal
            precision is the contract (plan §4 invariant: "returns
            ``Decimal``, never ``float``").

        Raises:
            InstrumentNotFoundError: if no OPTSTK rows exist for
                the underlying in the loaded catalog (the underlying
                is either unknown to Dhan or has no listed options).
        """
        upper = (underlying or "").strip().upper()
        if not upper:
            raise InstrumentNotFoundError(
                underlying or "", "NSE_FNO", reason="Empty underlying input"
            )
        # 1) Index static step
        if upper in INDEX_STRIKE_STEP:
            return Decimal(INDEX_STRIKE_STEP[upper])
        # 2) Commodity static step
        if upper in COMMODITY_STRIKE_STEP:
            return Decimal(str(COMMODITY_STRIKE_STEP[upper]))
        # 3) Auto-derive from the loaded catalog (Tradehull's
        #    dhan_equity_step_creation algorithm).
        return self._derive_equity_strike_step(upper)

    def _derive_equity_strike_step(self, underlying: str) -> Decimal:
        """Tradehull's ``dhan_equity_step_creation`` algorithm.

        Steps (verbatim from plan §6.2.2):

        1. Filter the catalog's ``_options_by_underlying[underlying]``
           to ``exchange_segment == NSE_FNO`` and ``instrument_type == "OPTSTK"``
           and ``option_type == "CE"`` (the CE half of the chain is
           sufficient — both CE and PE share the same step).
        2. Drop the rows whose expiry has already passed.
        3. Pick the row group with the nearest expiry.
        4. Sort the strike prices, compute consecutive differences,
           and return the **mode**.
        5. Wrap the result in :class:`Decimal` — integer-valued
           steps are returned as int, fractional steps preserve
           the precision.

        Raises:
            InstrumentNotFoundError: if the underlying is unknown
                to the catalog (no options) or the options don't
                have enough strikes to compute a step.
        """
        with self._lock:
            catalog = self._indexes.catalog
        with catalog._lock:
            options = list(catalog._options_by_underlying.get(underlying, []))
        # Filter to OPTSTK + NSE_FNO + CE, mirroring Tradehull.
        candidates = [
            d
            for d in options
            if d.exchange_segment == ExchangeSegment.NSE_FNO
            and (d.instrument_type or "").upper() == "OPTSTK"
            and (d.option_type or "").upper() == "CE"
            and d.strike_price_paisa is not None
        ]
        if not candidates:
            raise InstrumentNotFoundError(
                underlying,
                "NSE_FNO",
                reason=f"No OPTSTK rows for underlying {underlying!r}",
            )
        # Live expiries only.
        today_iso = date.today().isoformat()
        live = [d for d in candidates if d.expiry is None or d.expiry >= today_iso]
        if not live:
            raise InstrumentNotFoundError(
                underlying,
                "NSE_FNO",
                reason=f"All OPTSTK rows for {underlying!r} have expired",
            )
        # Pick the nearest-expiry group.
        nearest_expiry = min(d.expiry for d in live)
        nearest_group = [d for d in live if d.expiry == nearest_expiry]
        if len(nearest_group) < 2:
            raise InstrumentNotFoundError(
                underlying,
                "NSE_FNO",
                reason=(
                    f"Only {len(nearest_group)} OPTSTK row(s) for {underlying!r} "
                    f"on nearest expiry {nearest_expiry}; need ≥ 2 to compute a step"
                ),
            )
        # Tradehull sorts strikes as integers; we keep paisa units and
        # convert to rupees at the end so the mode is in the same unit
        # as the static tables (rupees).
        strikes = sorted(d.strike_price_paisa for d in nearest_group)
        diffs = [strikes[i + 1] - strikes[i] for i in range(len(strikes) - 1)]
        # Mode of the consecutive differences.
        step_paisa, _ = Counter(diffs).most_common(1)[0]
        # Convert paisa → rupees; preserve fractional precision.
        rupees = Decimal(step_paisa) / Decimal(100)
        # If the value is exactly integer-valued, return int form for
        # parity with the static tables.  Otherwise return the Decimal
        # as-is.
        if rupees == rupees.to_integral_value():
            return Decimal(int(rupees))
        return rupees

    # ── Discovery (M2) ─────────────────────────────────────────────────────

    def search_symbols(
        self,
        query: str,
        *,
        exchange: str | ExchangeSegment | None = None,
        limit: int = 20,
    ) -> list[DhanInstrumentDefinition]:
        """Case-insensitive prefix/substring search over trading and custom symbols.

        Ranking:

        1. **Exact match** on trading symbol (or custom symbol) wins
           the first slot.
        2. **Prefix match** on trading symbol (e.g. query ``RELI`` →
           ``RELIANCE``) is preferred over substring matches.
        3. **Prefix match** on custom symbol is next.
        4. **Substring match** on trading or custom symbol comes last.
        5. Within each tier, results are sorted alphabetically by
           ``trading_symbol``.

        If ``exchange`` is given, results are filtered to that segment
        (NSE, BSE, NSE_FNO, etc.) before the ranking.  At most
        ``limit`` results are returned.
        """
        with self._lock:
            catalog = self._indexes.catalog
        q = (query or "").strip().upper()
        if not q:
            return []

        segment_filter: ExchangeSegment | None = None
        if exchange is not None:
            raw = exchange.value if isinstance(exchange, ExchangeSegment) else exchange
            try:
                segment_filter = self.resolve_exchange_segment(raw)
            except ValueError:
                segment_filter = None  # unknown exchange → no filter

        # Pull all candidates from the catalog first; the trading-symbol
        # and custom-symbol indexes are the primary source.
        with catalog._lock:
            trading_buckets = list(catalog._by_trading_symbol.items())
            custom_buckets = list(catalog._by_custom_symbol.items())

        seen: set[tuple[str, str]] = set()
        candidates: list[DhanInstrumentDefinition] = []
        for sym, defs in trading_buckets:
            if not (q == sym or sym.startswith(q) or q in sym):
                continue
            for d in defs:
                if segment_filter is not None and d.exchange_segment != segment_filter:
                    continue
                key = (d.security_id, d.exchange_segment.value)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(d)
        for sym, defs in custom_buckets:
            if not (q == sym or sym.startswith(q) or q in sym):
                continue
            for d in defs:
                if segment_filter is not None and d.exchange_segment != segment_filter:
                    continue
                key = (d.security_id, d.exchange_segment.value)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(d)

        # Rank: exact > prefix-trading > prefix-custom > substring
        def rank(defn: DhanInstrumentDefinition) -> tuple[int, str, str]:
            ts = defn.symbol.upper()
            cs = defn.canonical_symbol.upper()
            if ts == q or cs == q:
                tier = 0
            elif ts.startswith(q) or cs.startswith(q):
                tier = 1
            else:
                tier = 2
            return (tier, ts, d.exchange_segment.value)

        candidates.sort(key=rank)
        return candidates[: max(0, limit)]

    def get_option_chain(
        self, underlying: str, expiry: date | None = None
    ) -> list[DhanInstrumentDefinition]:
        """Return all live (or expiry-filtered) option contracts for ``underlying``.

        "Live" means the contract's ``expiry`` is on or after today
        (i.e. the option has not yet expired in the catalog).  When
        ``expiry`` is provided, the result is restricted to that exact
        ISO date; if no contracts match, the list is empty (callers can
        decide whether to treat that as a hard error).

        The result is sorted by ``(expiry, strike, option_type)`` so the
        caller can render a strike ladder or a chain view.

        Raises:
            InstrumentNotFoundError: if no live options exist for the
                underlying at all (this is the only case where we
                fail-loud — an unknown underlying is a hard bug).
        """
        with self._lock:
            catalog = self._indexes.catalog
        underlying_u = (underlying or "").strip().upper()
        if not underlying_u:
            raise InstrumentNotFoundError(
                underlying or "", "NSE_FNO", reason="Empty underlying input"
            )
        contracts = self._options_for(catalog, underlying_u)
        if not contracts:
            raise InstrumentNotFoundError(
                underlying_u,
                "NSE_FNO",
                reason=f"No options found for underlying {underlying_u!r}",
            )
        today_iso = date.today().isoformat()
        live = [
            d
            for d in contracts
            if d.expiry is not None
            and d.expiry >= today_iso
            and (expiry is None or d.expiry == expiry.isoformat())
        ]
        # Stable order: expiry → strike → option type
        live.sort(
            key=lambda d: (
                d.expiry or "9999-12-31",
                d.strike_price_paisa or 0,
                d.option_type,
            )
        )
        if not live and expiry is not None:
            # Don't raise here — the caller asked for a specific date
            # and may want an empty list.  Only raise when the
            # underlying is completely unknown.
            return []
        return live

    def get_futures(self, underlying: str) -> list[DhanInstrumentDefinition]:
        """Return all live futures for ``underlying``, sorted by expiry.

        A contract is "live" if its ``expiry`` is ``None`` (perpetual
        — rare in Indian markets but possible) or on/after today's
        date.  The returned list is sorted by ascending expiry so the
        caller can pick the front-month with ``[0]``.

        Raises:
            InstrumentNotFoundError: if no live futures exist for
                ``underlying`` (hard fail — an unknown underlying is
                a real bug, not a no-op).
        """
        with self._lock:
            catalog = self._indexes.catalog
        underlying_u = (underlying or "").strip().upper()
        if not underlying_u:
            raise InstrumentNotFoundError(
                underlying or "", "NSE_FNO", reason="Empty underlying input"
            )
        contracts = self._futures_for(catalog, underlying_u)
        if not contracts:
            raise InstrumentNotFoundError(
                underlying_u,
                "NSE_FNO",
                reason=f"No futures found for underlying {underlying_u!r}",
            )
        today_iso = date.today().isoformat()
        live = [d for d in contracts if d.expiry is None or d.expiry >= today_iso]
        live.sort(key=lambda d: d.expiry or "9999-12-31")
        return live

    # ── Validation (M2) ────────────────────────────────────────────────────

    def validate_symbol(self, symbol: str, exchange: str) -> bool:
        """Return ``True`` iff ``resolve_symbol(symbol, exchange)`` is a single match.

        This is the boolean projection of :meth:`resolve_symbol` used
        by validators and CLI guards.  Any internal exception
        (resolution error, ambiguity, strict-mode failure) is caught
        and reported as ``False`` — the caller does not need to
        distinguish "no such symbol" from "ambiguous symbol".
        """
        try:
            result = self.resolve_symbol(symbol, exchange)
        except Exception:  # pragma: no cover - defensive guard
            return False
        return bool(result.is_single and result.definition is not None)

    # ── Diagnostics (M2) ───────────────────────────────────────────────────

    def diagnostics(self, symbol: str, exchange: str) -> str:
        """Render a human-readable diagnostic block for the CLI.

        On a successful single resolution, the block lists every
        attribute of the matched definition (trading symbol, custom
        symbol, security ID, exchange, segment, instrument type,
        ISIN, expiry, strike, option type).  On a failed resolution
        (unknown or ambiguous) the block lists the failure reason
        and, where applicable, the candidate list so the operator
        can disambiguate.
        """
        lines: list[str] = []
        result = self.resolve_symbol(symbol, exchange)
        ex_display = (
            exchange.value if isinstance(exchange, ExchangeSegment) else (exchange or "")
        ).upper()
        sym_display = (symbol or "").strip()
        lines.append(f"Input Symbol:    {sym_display}")
        lines.append(f"Input Exchange:  {ex_display}")

        if result.is_single and result.definition is not None:
            d = result.definition
            lines.append("Result:          SUCCESS")
            lines.append("")
            lines.append("Matched Record:")
            lines.append(f"  Trading Symbol:    {d.symbol}")
            lines.append(f"  Custom Symbol:     {d.canonical_symbol}")
            lines.append(f"  Security ID:       {d.security_id}")
            lines.append(f"  Exchange:          {d.exchange}")
            lines.append(f"  Segment:           {d.exchange_segment.value}")
            lines.append(f"  Instrument Type:   {d.instrument_type}")
            if d.isin:
                lines.append(f"  ISIN:              {d.isin}")
            if d.expiry:
                lines.append(f"  Expiry:            {d.expiry}")
            if d.strike is not None:
                lines.append(f"  Strike:            {d.strike}")
            if d.option_type:
                lines.append(f"  Option Type:       {d.option_type}")
            if d.underlying:
                lines.append(f"  Underlying:        {d.underlying}")
            if d.lot_size:
                lines.append(f"  Lot Size:          {d.lot_size}")
            lines.append(f"  Reason:            {result.reason}")
            return "\n".join(lines)

        # Failure path
        if result.is_ambiguous:
            lines.append("Result:          AMBIGUOUS")
        else:
            lines.append("Result:          Lookup Failed")
        lines.append(f"Reason:          {result.reason}")
        if result.candidates:
            lines.append("")
            lines.append("Available Matches:")
            for d in result.candidates:
                lines.append(f"  {d.symbol} {d.exchange_segment.value} ({d.security_id})")
        return "\n".join(lines)
