"""DhanInstrumentService — broker-internal instrument load + security mapping.

Composes :class:`InstrumentLoader`, :class:`SymbolResolver`, and
:class:`DhanIdentityProvider`. Gateways must only call ``load`` / ``resolve``
/ ``search`` / ``stats`` / ``is_loaded``. Wire refs (``resolve_ref``) are for
the connection / adapters only.
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Any

from brokers.common.instruments.carrier import BrokerWireRef, LoadStats, ResolvedInstrument
from brokers.dhan.identity.identity import DhanIdentityProvider, DhanInstrumentRef
from brokers.dhan.loader import InstrumentLoader
from brokers.dhan.resolver import SymbolResolver

logger = logging.getLogger(__name__)


class DhanInstrumentService:
    """Dhan implementation of :class:`BrokerInstrumentService`."""

    def __init__(
        self,
        resolver: SymbolResolver | None = None,
        identity: DhanIdentityProvider | None = None,
    ) -> None:
        self._resolver = resolver or SymbolResolver()
        self._identity = identity or DhanIdentityProvider(self._resolver)

    @property
    def resolver(self) -> SymbolResolver:
        """Underlying SymbolResolver (internal Dhan callers / lifecycle)."""
        return self._resolver

    @property
    def identity(self) -> DhanIdentityProvider:
        """Single source of truth for symbol→security_id."""
        return self._identity

    # ── BrokerInstrumentService ─────────────────────────────────────────

    def load(
        self,
        source: str | None = None,
        *,
        force_refresh: bool = False,
    ) -> LoadStats:
        """Load instrument master into the in-memory resolver."""
        start = time.monotonic()
        if source is not None:
            if source.startswith(("http://", "https://")):
                rows = InstrumentLoader.load_from_url(source)
            else:
                rows = InstrumentLoader.load_from_file(source)
            src_label = source
        elif force_refresh:
            rows = InstrumentLoader.load_cached(force_refresh=True)
            src_label = "force_refresh"
        else:
            rows = InstrumentLoader.load_cached()
            src_label = "cached"
        load_time = time.monotonic() - start

        logger.info(
            "instrument_load_completed",
            extra={
                "count": len(rows),
                "load_time_s": round(load_time, 2),
                "source": src_label,
            },
        )

        start = time.monotonic()
        stats = self._resolver.load_from_rows(rows)
        memory_time = time.monotonic() - start

        skipped = int(stats.get("skipped", 0))
        total = int(stats.get("total", len(rows)))
        skip_rate = float(stats.get("skip_rate", 0.0))
        if total > 0 and skipped / total > 0.01:
            logger.warning(
                "instrument_load_skipped_high",
                extra={
                    "skipped": skipped,
                    "total": total,
                    "skip_rate": round(skipped / total, 4),
                    "threshold": 0.01,
                },
            )

        logger.info(
            "instrument_memory_load_completed",
            extra={
                "count": len(rows),
                "skipped": skipped,
                "memory_time_s": round(memory_time, 2),
            },
        )
        return LoadStats(
            total=total,
            skipped=skipped,
            skip_rate=skip_rate,
            source=src_label,
        )

    def resolve(self, symbol: str, exchange: str) -> ResolvedInstrument:
        """Canonical resolve — no wire identifiers."""
        inst = self._resolver.resolve(symbol, exchange)
        return ResolvedInstrument(
            symbol=inst.symbol,
            exchange=inst.exchange.value if hasattr(inst.exchange, "value") else str(inst.exchange),
            instrument_type=(
                inst.instrument_type.value
                if hasattr(inst.instrument_type, "value")
                else str(inst.instrument_type)
            ),
            lot_size=int(inst.lot_size or 1),
            tick_size=(
                inst.tick_size
                if isinstance(inst.tick_size, Decimal)
                else Decimal(str(inst.tick_size or "0.05"))
            ),
            expiry=inst.expiry,
            strike=inst.strike_price,
            option_type=(
                inst.option_type.value
                if inst.option_type is not None and hasattr(inst.option_type, "value")
                else (str(inst.option_type) if inst.option_type else None)
            ),
            underlying=inst.underlying,
            canonical_symbol=inst.canonical_symbol,
            name=inst.name,
        )

    def resolve_ref(
        self,
        symbol: str,
        exchange: str,
        *,
        expected_segment: str | None = None,
    ) -> BrokerWireRef:
        """Opaque wire ref for connection / adapters (not for gateways)."""
        ref = self._identity.resolve_ref(symbol, exchange, expected_segment=expected_segment)
        return self._to_wire_ref(ref)

    def resolve_dhan_ref(
        self,
        symbol: str,
        exchange: str,
        *,
        expected_segment: str | None = None,
    ) -> DhanInstrumentRef:
        """Typed Dhan carrier — preferred inside brokers/dhan/**."""
        return self._identity.resolve_ref(symbol, exchange, expected_segment=expected_segment)

    def search(self, query: str, *, limit: int = 20) -> list[dict]:
        """Search returning canonical dicts (no wire identifiers)."""
        results: list[dict] = []
        q = query.upper().strip()
        for inst in self._resolver.all_instruments():
            if q in inst.symbol.upper() or q in (inst.canonical_symbol or "").upper():
                exchange = (
                    inst.exchange.value if hasattr(inst.exchange, "value") else str(inst.exchange)
                )
                results.append(
                    {
                        "symbol": inst.symbol,
                        "exchange": exchange,
                        "type": inst.instrument_type.value,
                        "name": inst.canonical_symbol or inst.name,
                    }
                )
                if len(results) >= limit:
                    break
        return results

    def stats(self) -> dict:
        base = self._resolver.stats()
        return {
            "loaded": bool(base.get("loaded", self._resolver._loaded)),
            "total": int(base.get("total", 0)),
            "issue_count": self._identity.issue_count,
            "synthetic_index_count": self._identity.synthetic_index_count,
        }

    def is_loaded(self) -> bool:
        return bool(self._resolver._loaded)

    def all_instruments(self) -> list[Any]:
        return self._resolver.all_instruments()

    def load_from_rows(self, rows: Any) -> dict[str, int | float]:
        """Populate resolver from pre-parsed rows (tests / offline fixtures)."""
        return self._resolver.load_from_rows(rows)

    @staticmethod
    def _to_wire_ref(ref: DhanInstrumentRef) -> BrokerWireRef:
        return BrokerWireRef(
            symbol=ref.symbol,
            exchange=ref.exchange.value if hasattr(ref.exchange, "value") else str(ref.exchange),
            wire={
                "exchange_segment": ref.exchange_segment,
                "security_id": ref.security_id_str(),
            },
        )
