"""UpstoxInstrumentService — broker-internal instrument load + security mapping.

Composes :class:`UpstoxInstrumentLoader`, :class:`UpstoxInstrumentResolver`,
and :class:`UpstoxSegmentMapper`. Gateways call ``load`` / ``resolve`` /
``search`` with canonical symbols; ``resolve_ref`` (instrument_key) is for
connection / adapters only.
"""

from __future__ import annotations

import contextlib
import logging
import time
from decimal import Decimal
from pathlib import Path

from brokers.common.instruments.carrier import BrokerWireRef, LoadStats, ResolvedInstrument
from brokers.providers.upstox.instruments.loader import UpstoxInstrumentLoader
from brokers.providers.upstox.instruments.resolver import UpstoxInstrumentResolver

logger = logging.getLogger(__name__)

_DEFAULT_CACHE = Path(".cache/upstox/complete.json.gz")


class UpstoxInstrumentService:
    """Upstox implementation of :class:`BrokerInstrumentService`."""

    def __init__(
        self,
        resolver: UpstoxInstrumentResolver | None = None,
        loader: UpstoxInstrumentLoader | None = None,
    ) -> None:
        self._resolver = resolver or UpstoxInstrumentResolver()
        self._loader = loader or UpstoxInstrumentLoader()

    @property
    def resolver(self) -> UpstoxInstrumentResolver:
        """Underlying resolver (adapters that still take UpstoxInstrumentResolver)."""
        return self._resolver

    @property
    def loader(self) -> UpstoxInstrumentLoader:
        return self._loader

    # ── BrokerInstrumentService ─────────────────────────────────────────

    def load(
        self,
        source: str | None = None,
        *,
        force_refresh: bool = False,
    ) -> LoadStats:
        """Load instrument definitions from cache or download."""
        if source:
            path = Path(source)
        else:
            # force_refresh: bypass cache validity by deleting then re-download
            if force_refresh and _DEFAULT_CACHE.exists():
                with contextlib.suppress(OSError):
                    _DEFAULT_CACHE.unlink()
            path = self._loader.download(_DEFAULT_CACHE)

        start = time.monotonic()
        defs = self._loader.load(path)
        load_time = time.monotonic() - start
        logger.info(
            "instrument_load_completed",
            extra={
                "count": len(defs),
                "load_time_s": round(load_time, 2),
                "source": source or "cached",
            },
        )

        start = time.monotonic()
        self._resolver.register_many(defs)
        memory_time = time.monotonic() - start
        logger.info(
            "instrument_memory_load_completed",
            extra={"count": len(defs), "memory_time_s": round(memory_time, 2)},
        )
        return LoadStats(
            total=len(defs),
            skipped=0,
            skip_rate=0.0,
            source=source or "cached",
        )

    def resolve(self, symbol: str, exchange: str) -> ResolvedInstrument:
        """Canonical resolve — no wire identifiers."""
        key = self.resolve_instrument_key(symbol, exchange)
        defn = self._resolver.resolve(instrument_key=key)
        if defn is None:
            defn = self._resolver.require(symbol=symbol, exchange_segment=exchange)
        return ResolvedInstrument(
            symbol=defn.symbol or defn.trading_symbol,
            exchange=defn.exchange_segment or exchange,
            instrument_type=defn.instrument_type or "EQUITY",
            lot_size=int(defn.lot_size or 1),
            tick_size=Decimal(str(defn.tick_size or "0.05")),
            expiry=defn.expiry,
            strike=Decimal(str(defn.strike)) if defn.strike is not None else None,
            option_type=defn.option_type,
            underlying=defn.underlying_symbol,
            canonical_symbol=defn.name or None,
            name=defn.name or None,
        )

    def resolve_ref(
        self,
        symbol: str,
        exchange: str,
        *,
        expected_segment: str | None = None,
    ) -> BrokerWireRef:
        """Opaque wire ref carrying Upstox ``instrument_key``."""
        key = self.resolve_instrument_key(symbol, exchange)
        if expected_segment is not None:
            # Soft check: instrument_key prefix should match expected wire segment
            prefix = key.split("|", 1)[0] if "|" in key else ""
            if prefix and prefix != expected_segment:
                raise ValueError(
                    f"Upstox resolve({symbol!r}, {exchange!r}) returned key "
                    f"{key!r} but caller required segment {expected_segment!r}"
                )
        return BrokerWireRef(
            symbol=symbol,
            exchange=exchange,
            wire={"instrument_key": key},
        )

    def resolve_instrument_key(self, symbol: str, exchange: str) -> str:
        """Resolve canonical symbol to Upstox instrument_key (internal).

        Resolution priority:
        1. Hardcoded index mapping (NIFTY, BANKNIFTY, …)
        2. Bare commodity underlying on MCX (e.g. "GOLD", "CRUDEOIL") ->
           nearest-expiry future contract
        3. Instrument master lookup
        4. Fallback: ``{segment}|{symbol}``
        """
        from brokers.providers.upstox.mappers.domain_mapper import UpstoxDomainMapper
        from config.indices import index_upstox_key

        idx_key = index_upstox_key(symbol)
        if idx_key is not None:
            defn = self._resolver.resolve(instrument_key=idx_key)
            if defn:
                return defn.instrument_key
            return idx_key

        segment = UpstoxDomainMapper.segment_to_wire(exchange)
        if segment == "NSE":
            segment = "NSE_EQ"
        elif segment == "BSE":
            segment = "BSE_EQ"

        # MCX instruments don't have a spot/index instrument the way equities
        # do -- a bare underlying (no spaces, i.e. not a full trading symbol
        # like "GOLD FUT 05 AUG 26") means the caller wants the tradable
        # commodity contract. Registration leaves ``symbol`` blank on MCX
        # instrument records, so the resolver's dict lookup depends on
        # collision-prone alternate keys and either misses entirely (no
        # match at all) or matches an arbitrary option leg instead of the
        # future. list_future_contracts() filters strictly by
        # underlying_symbol and sorts by expiry, so it always resolves
        # deterministically to the near-month future.
        if segment == "MCX_FO" and " " not in symbol.strip():
            # list_future_contracts() doesn't filter by exchange_segment --
            # the same commodity is often cross-listed under NSE_COM too,
            # so an unfiltered pick can silently return an NSE_COM contract
            # (no MCX market data => zero LTP) instead of the MCX one.
            contracts = [
                c
                for c in self._resolver.list_future_contracts(symbol)
                if c.exchange_segment == segment
            ]
            if contracts:
                return contracts[0].instrument_key

        defn = self._resolver.resolve(symbol=symbol, exchange_segment=segment)
        if defn:
            return defn.instrument_key
        return f"{segment}|{symbol}"

    def search(self, query: str, *, limit: int = 20) -> list[dict]:
        results: list[dict] = []
        q = query.upper().strip()
        defs = self._resolver.search(q, limit=limit)
        for d in defs:
            dct = d.model_dump() if hasattr(d, "model_dump") else d.dict()
            if not dct.get("symbol") and dct.get("trading_symbol"):
                dct["symbol"] = dct["trading_symbol"]
            results.append(dct)
        return results[:limit]

    def stats(self) -> dict:
        return {
            "loaded": self._resolver.is_loaded(),
            "total": len(self._resolver),
        }

    def is_loaded(self) -> bool:
        return self._resolver.is_loaded()
