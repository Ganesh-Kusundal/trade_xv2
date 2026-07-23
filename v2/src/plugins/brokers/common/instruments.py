"""Shared broker instrument resolution — canonical vs opaque wire-ref split.

``ResolvedInstrument`` is what gateways may see: canonical symbol/exchange,
no broker wire identifiers. ``BrokerWireRef`` is opaque — only the wire
adapter/connection that builds HTTP/WebSocket payloads may read ``.wire``.

Each broker (Dhan/Upstox) previously kept its own private
``dict[str, str]`` + reverse dict for symbol <-> wire-id mapping (flagged in
the v2-vs-legacy broker review as duplicated, dead-end infrastructure — legacy's
``BrokerInstrumentService``/``SymbolResolver`` proves this is worth sharing).
``InMemoryInstrumentResolver`` is that shared store; ``DhanWire``/``UpstoxWire``
delegate to one instance each instead of reimplementing the same two dicts.

``load_from_rows`` accepts pre-fetched instrument-master rows (shape:
``{"instrument_id": "NSE:RELIANCE", "wire": {"security_id": "1333"}}``) so a
future bulk loader (fetching the real Dhan/Upstox scrip master) can populate
the resolver without changing this module — that fetch itself is out of scope
here (no live instrument-master integration to verify against in this pass).
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

from domain.symbols import normalize_symbol
from domain.value_objects import InstrumentId
from plugins.brokers.common.instruments_keys import generate_alternate_keys

logger = logging.getLogger(__name__)


# Exchange series/segment suffixes (NSE/BSE) stripped from symbols so
# "RELIANCE-EQ" and "RELIANCE" resolve to the same instrument (spec §3.1).
_SUFFIX = re.compile(r"[-_](EQ|BE|BL|BZ|MC|NC|NZ|SM|SO|TT)\s*$", re.IGNORECASE)


def _strip_symbol_suffix(sym: str) -> str:
    sym = sym.strip().upper()
    return _SUFFIX.sub("", sym)


@dataclass(frozen=True, slots=True)
class ResolvedInstrument:
    """Canonical instrument record — no broker wire identifiers, ever."""

    instrument_id: InstrumentId
    exchange: str
    symbol: str
    canonical_symbol: str | None = None
    instrument_type: str | None = None
    underlying: str | None = None
    expiry: str | None = None
    strike: Any | None = None
    option_type: str | None = None


@dataclass(frozen=True, slots=True)
class BrokerWireRef:
    """Opaque broker-native identity. Gateways must never read ``wire``."""

    instrument_id: InstrumentId
    wire: dict[str, Any]

    def require(self, key: str) -> Any:
        if key not in self.wire:
            raise KeyError(f"BrokerWireRef missing wire key {key!r}")
        return self.wire[key]


@dataclass(frozen=True, slots=True)
class LoadStats:
    total: int = 0
    source: str = "manual"


@runtime_checkable
class BrokerInstrumentService(Protocol):
    """Per-broker instrument master + wire-id mapping — common port."""

    def register(self, instrument_id: InstrumentId, wire: dict[str, Any]) -> None: ...

    def load_from_rows(self, rows: list[dict[str, Any]], *, source: str = "bulk") -> LoadStats: ...

    def resolve_ref(self, instrument_id: InstrumentId) -> BrokerWireRef: ...

    def reverse(self, key: str, value: str) -> InstrumentId | None: ...

    def is_loaded(self) -> bool: ...

    def stats(self) -> LoadStats: ...


class InMemoryInstrumentResolver:
    """Generic in-memory instrument master — manual register + bulk load.

    ``_reverse`` is a dict-of-dicts (wire key -> wire value -> InstrumentId)
    maintained alongside ``_wire`` so ``reverse()`` is O(1) even with a
    ~220k-row broker instrument master, instead of scanning every entry.
    """

    def __init__(
        self,
        index_fallback: Callable[[InstrumentId], dict | None] | None = None,
    ) -> None:
        self._wire: dict[str, dict[str, Any]] = {}
        self._reverse: dict[str, dict[str, InstrumentId]] = {}
        self._meta: dict[str, ResolvedInstrument] = {}
        self._stats = LoadStats()
        self._lock = threading.Lock()
        self._index_fallback = index_fallback

    # -- alias derivation (shared wheel, zero-parity with legacy) -------

    def _alias_keys(self, instrument_id: InstrumentId, wire: dict[str, Any]) -> list[str]:
        """Derive all lookup keys (incl. alternate forms) for *instrument_id*.

        The canonical ``instrument_id.value`` (``EXCHANGE:SYMBOL``) is always
        included; ``generate_alternate_keys`` adds CE/PE, spaced/compact and
        weekly option / future variants and de-duplicates via a ``seen`` set
        so one instrument never collides across text forms. Every alias is
        prefixed with the exchange (``EXCHANGE:ALIAS``) to keep the
        collision-safe ``(symbol, exchange)`` scoping legacy uses.
        """
        keys = [instrument_id.value]
        # Stripped canonical variant (e.g. NSE:RELIANCE-EQ -> NSE:RELIANCE).
        if ":" in instrument_id.value:
            _exch, _sym = instrument_id.value.split(":", 1)
            stripped_canon = f"{_exch}:{_strip_symbol_suffix(_sym)}"
        else:
            stripped_canon = _strip_symbol_suffix(instrument_id.value)
        if stripped_canon != instrument_id.value:
            keys.append(stripped_canon)
        meta = self._meta.get(instrument_id.value)
        exch = meta.exchange if meta is not None else None
        if exch is None and ":" in instrument_id.value:
            exch = instrument_id.value.split(":", 1)[0]
        if meta is not None and meta.symbol:
            stripped_sym = _strip_symbol_suffix(meta.symbol)
            alt: list[str] = []
            seen_alt: set[str] = set()
            for sym_variant in (stripped_sym, meta.symbol):
                for a in generate_alternate_keys(
                    symbol=sym_variant,
                    inst_type=meta.instrument_type or "",
                    expiry=meta.expiry,
                    strike=meta.strike,
                    option_type=meta.option_type,
                    underlying=meta.underlying,
                    canonical_symbol=meta.canonical_symbol,
                ):
                    if a not in seen_alt:
                        seen_alt.add(a)
                        alt.append(a)
            prefix = f"{exch}:" if exch else ""
            keys.extend(f"{prefix}{a}" for a in alt)
        return keys

    def register(
        self,
        instrument_id: InstrumentId,
        wire: dict[str, Any],
        *,
        symbol: str | None = None,
        exchange: str | None = None,
        instrument_type: str | None = None,
        underlying: str | None = None,
        expiry: str | None = None,
        strike: Any | None = None,
        option_type: str | None = None,
        canonical_symbol: str | None = None,
    ) -> None:
        """Register a wire reference, fanning out alias keys when metadata given.

        ``symbol``/``exchange`` are required for alias generation; if omitted,
        only the canonical ``instrument_id`` key is stored (back-compat).
        """
        if symbol is None:
            # Derive a bare symbol from the canonical id (EXCHANGE:SYMBOL).
            parts = instrument_id.value.split(":", 1)
            symbol = parts[1] if len(parts) == 2 else instrument_id.value
        if exchange is None:
            parts = instrument_id.value.split(":", 1)
            exchange = parts[0] if len(parts) == 2 else ""
        # Persist canonical metadata so load_from_rows / later resolves keep it.
        self._meta[instrument_id.value] = ResolvedInstrument(
            instrument_id=instrument_id,
            exchange=exchange,
            symbol=_strip_symbol_suffix(symbol),
            canonical_symbol=canonical_symbol,
            instrument_type=instrument_type,
            underlying=underlying,
            expiry=expiry,
            strike=strike,
            option_type=option_type,
        )
        with self._lock:
            self._register_locked(instrument_id, wire)

    def _register_locked(self, instrument_id: InstrumentId, wire: dict[str, Any]) -> None:
        # Drop the previous wire's reverse entries for this iid so an
        # O(1) reverse lookup can't point at a stale wire id after a
        # re-register (mirrors legacy invariant).
        old = self._wire.get(instrument_id.value)
        if old:
            for key, value in old.items():
                bucket = self._reverse.get(key)
                if bucket is not None and bucket.get(str(value)) == instrument_id:
                    del bucket[str(value)]
        for key in self._alias_keys(instrument_id, wire):
            self._wire[key] = dict(wire)
            for wkey, value in wire.items():
                self._reverse.setdefault(wkey, {})[str(value)] = instrument_id

    def load_from_rows(self, rows: list[dict[str, Any]], *, source: str = "bulk") -> LoadStats:
        """Build a fresh wire/reverse index off to the side, then swap in one
        step — a concurrent reader never sees a partially-loaded resolver
        mid-refresh. Duplicate canonical ids are logged (last-write-wins).

        Each row may carry an ``alias_fields`` dict (symbol/exchange/
        instrument_type/underlying/expiry/strike/option_type/canonical_symbol)
        to enable alternate-key fan-out; without it only the canonical
        ``instrument_id`` is stored.
        """
        new_wire: dict[str, dict[str, Any]] = {}
        new_reverse: dict[str, dict[str, InstrumentId]] = {}
        new_meta: dict[str, ResolvedInstrument] = {}
        duplicates = 0
        count = 0
        for row in rows:
            raw_iid = row.get("instrument_id")
            wire = row.get("wire")
            if not raw_iid or wire is None:
                continue
            iid = raw_iid if isinstance(raw_iid, InstrumentId) else InstrumentId.parse(str(raw_iid))
            af = row.get("alias_fields") or {}
            symbol = af.get("symbol")
            if symbol is None:
                parts = iid.value.split(":", 1)
                symbol = parts[1] if len(parts) == 2 else iid.value
            exchange = af.get("exchange") or (
                iid.value.split(":", 1)[0] if ":" in iid.value else ""
            )
            meta = ResolvedInstrument(
                instrument_id=iid,
                exchange=exchange,
                symbol=symbol,
                canonical_symbol=af.get("canonical_symbol"),
                instrument_type=af.get("instrument_type"),
                underlying=af.get("underlying"),
                expiry=af.get("expiry"),
                strike=af.get("strike"),
                option_type=af.get("option_type"),
            )
            new_meta[iid.value] = meta
            alt = [iid.value]
            prefix = f"{exchange}:" if exchange else ""
            alt.extend(
                f"{prefix}{a}"
                for a in generate_alternate_keys(
                    symbol=meta.symbol,
                    inst_type=meta.instrument_type or "",
                    expiry=meta.expiry,
                    strike=meta.strike,
                    option_type=meta.option_type,
                    underlying=meta.underlying,
                    canonical_symbol=meta.canonical_symbol,
                )
            )
            if iid.value in new_wire:
                duplicates += 1
            for key in alt:
                new_wire[key] = dict(wire)
                for wkey, value in wire.items():
                    new_reverse.setdefault(wkey, {})[str(value)] = iid
            count += 1
        with self._lock:
            self._wire = new_wire
            self._reverse = new_reverse
            self._meta = new_meta
            self._stats = LoadStats(total=len(new_wire), source=source)
        if duplicates:
            logger.warning(
                "instrument_resolver_duplicates: %d duplicate instrument ids in %r load (last-write-wins)",
                duplicates,
                source,
            )
        return self._stats

    def resolve_ref(self, instrument_id: InstrumentId) -> BrokerWireRef:
        wire = self._wire.get(instrument_id.value)
        if wire is None:
            # Try a normalized alias lookup (e.g. "NIFTY50" vs "NIFTY 50").
            key = normalize_symbol(instrument_id.value.replace(":", " "))
            wire = self._wire.get(key)
        if wire is None:
            # Strip exchange series suffix (e.g. NSE:RELIANCE-EQ -> NSE:RELIANCE).
            if ":" in instrument_id.value:
                exch, sym = instrument_id.value.split(":", 1)
                stripped = f"{exch}:{_strip_symbol_suffix(sym)}"
            else:
                stripped = _strip_symbol_suffix(instrument_id.value)
            wire = self._wire.get(stripped)
            if wire is None:
                wire = self._wire.get(normalize_symbol(stripped.replace(":", " ")))
        if wire is None:
            # Broker-specific index registry fallback — covers bare index
            # symbols (NIFTY, BANKNIFTY, ...) when the master isn't loaded.
            if self._index_fallback is not None:
                fallback_wire = self._index_fallback(instrument_id)
                if fallback_wire is not None:
                    return BrokerWireRef(instrument_id=instrument_id, wire=fallback_wire)
            raise KeyError(f"no wire ref registered for {instrument_id.value}")
        return BrokerWireRef(instrument_id=instrument_id, wire=wire)

    def reverse(self, key: str, value: str) -> InstrumentId | None:
        """Find the canonical id whose wire[key] == value (native → canonical). O(1)."""
        return self._reverse.get(key, {}).get(value)

    def is_loaded(self) -> bool:
        return bool(self._wire)

    def stats(self) -> LoadStats:
        return self._stats
