"""In-memory instrument resolver.

Mirrors Trade_J ``UpstoxInstrumentResolver``: index by instrument_key, by
(symbol, exchange_segment), and prefix search.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Iterable

from .definition import UpstoxInstrumentDefinition


class UpstoxInstrumentResolver:
    """In-memory index of ``UpstoxInstrumentDefinition`` records."""

    def __init__(self) -> None:
        self._by_key: dict[str, UpstoxInstrumentDefinition] = {}
        self._by_symbol_segment: dict[tuple[str, str], UpstoxInstrumentDefinition] = {}
        self._by_symbol_index: dict[str, list[UpstoxInstrumentDefinition]] = defaultdict(list)
        self._lock = threading.RLock()
        self._loaded = False

    def is_loaded(self) -> bool:
        with self._lock:
            return self._loaded

    def reset(self) -> None:
        with self._lock:
            self._by_key.clear()
            self._by_symbol_segment.clear()
            self._by_symbol_index.clear()
            self._loaded = False

    def register(self, definition: UpstoxInstrumentDefinition) -> None:
        with self._lock:
            if definition.instrument_key:
                self._by_key[definition.instrument_key] = definition
            sym = definition.symbol or definition.trading_symbol
            if sym and definition.exchange_segment:
                key = (sym.upper(), definition.exchange_segment.upper())
                self._by_symbol_segment[key] = definition
                if sym:
                    self._by_symbol_index[sym.upper()].append(definition)
            self._loaded = True

    def register_many(self, definitions: Iterable[UpstoxInstrumentDefinition]) -> None:
        for d in definitions:
            self.register(d)

    def resolve(
        self,
        instrument_key: str | None = None,
        *,
        symbol: str | None = None,
        exchange_segment: str | None = None,
    ) -> UpstoxInstrumentDefinition | None:
        with self._lock:
            if instrument_key:
                d = self._by_key.get(instrument_key)
                if d is not None:
                    return d
            if symbol and exchange_segment:
                return self._by_symbol_segment.get((symbol.upper(), exchange_segment.upper()))
        return None

    def require(
        self,
        instrument_key: str | None = None,
        *,
        symbol: str | None = None,
        exchange_segment: str | None = None,
    ) -> UpstoxInstrumentDefinition:
        d = self.resolve(
            instrument_key=instrument_key, symbol=symbol, exchange_segment=exchange_segment
        )
        if d is None:
            ident = instrument_key or f"{symbol}@{exchange_segment}"
            raise ValueError(f"Upstox instrument not found: {ident}")
        return d

    def search(
        self, prefix: str, exchange_segment: str | None = None, limit: int = 50
    ) -> list[UpstoxInstrumentDefinition]:
        if not prefix:
            return []
        needle = prefix.upper()
        with self._lock:
            results: list[UpstoxInstrumentDefinition] = []
            for sym, defs in self._by_symbol_index.items():
                if not sym.startswith(needle):
                    continue
                for d in defs:
                    if exchange_segment and d.exchange_segment.upper() != exchange_segment.upper():
                        continue
                    results.append(d)
                    if len(results) >= limit:
                        return results
        return results

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._by_key.keys())

    def __len__(self) -> int:
        with self._lock:
            return len(self._by_key)
