"""Shared instrument resolution mixin for Dhan adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from brokers.dhan.instruments.resolution import ResolvedInstrument

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
