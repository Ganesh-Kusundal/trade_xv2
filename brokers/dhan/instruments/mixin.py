"""Shared instrument resolution mixin for Dhan adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from brokers.dhan.instruments.resolution import ResolvedInstrument
from brokers.dhan.mapper.dhan_segment_mapper import to_canonical_exchange, to_wire_value

if TYPE_CHECKING:
    from brokers.dhan.instrument_service import InstrumentService


class DhanInstrumentMixin:
    """Provides ``_resolve`` and ``_resolve_and_segment`` for Dhan adapters."""

    _instrument_service: InstrumentService

    def _resolve(self, symbol: str, exchange: str) -> ResolvedInstrument:
        if self._instrument_service is None:
            raise RuntimeError("No instrument service configured")
        return self._instrument_service.resolve_to_wire(symbol, exchange)

    def _resolve_and_segment(self, symbol: str, exchange: str) -> tuple[str, str]:
        """Return ``(security_id, wire_segment)`` for Dhan API payloads."""
        resolved = self._resolve(symbol, exchange)
        return resolved.security_id, resolved.wire_segment

    def _resolved_from_definition(self, defn) -> ResolvedInstrument:
        segment = defn.exchange_segment
        return ResolvedInstrument(
            definition=defn,
            security_id=defn.security_id,
            exchange_segment=segment,
            wire_segment=to_wire_value(segment),
            canonical_exchange=to_canonical_exchange(segment),
        )

    def _resolve_market(self, symbol: str, exchange: str) -> ResolvedInstrument:
        """Resolve a symbol for market-data calls, including historical routing."""
        from brokers.dhan.instrument_service import (
            AmbiguousInstrumentError,
            InstrumentNotFoundError,
        )

        result = self._instrument_service.resolve_symbol(symbol, exchange)
        if result.is_ambiguous:
            ex = (exchange or "").strip().upper()
            raise AmbiguousInstrumentError(
                (symbol or "").strip().upper(),
                ex,
                result.candidates,
            )
        defn = result.definition
        if defn is None:
            security_id = self._instrument_service.resolve_security_id(symbol, exchange)
            segment = (
                result.candidates[0].exchange_segment
                if result.candidates
                else self._instrument_service.resolve_exchange_segment(exchange)
            )
            defn = self._instrument_service.get_definition(security_id, segment)
            if defn is None:
                raise InstrumentNotFoundError(
                    symbol,
                    exchange,
                    candidates=result.candidates,
                    reason=(
                        "Cannot derive instrument type for market-data request: "
                        "no canonical definition found"
                    ),
                )
        return self._resolved_from_definition(defn)

    def _resolve_underlying_wire(
        self,
        underlying: str,
        exchange: str,
    ) -> ResolvedInstrument:
        """Resolve option-chain underlyings (e.g. NIFTY on NFO → IDX_I)."""
        segment = self._instrument_service.resolve_exchange_segment(exchange)
        defn = self._instrument_service.resolve_underlying(underlying, segment)
        return self._resolved_from_definition(defn)
