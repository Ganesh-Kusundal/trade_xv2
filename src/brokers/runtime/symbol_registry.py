"""SymbolRegistry — maps canonical instrument ids to broker symbols.

Thin coordinator over the existing ``infrastructure.instruments.InstrumentRegistry``
(canonical → broker identifier mapping). Reuses the shared registry rather than
re-implementing symbol resolution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from infrastructure.instruments import InstrumentRegistry

if TYPE_CHECKING:
    from domain.instruments.instrument_id import InstrumentId


class SymbolRegistry:
    """Broker symbol mapping backed by the shared instrument registry."""

    def __init__(self, registry: InstrumentRegistry | None = None) -> None:
        self._registry = registry or InstrumentRegistry()

    def lookup(self, instrument_id: InstrumentId) -> Any | None:
        try:
            return self._registry.lookup(instrument_id)
        except Exception:
            return None

    def register(self, instrument_id: InstrumentId, broker_symbol: Any) -> None:
        try:
            self._registry.register(instrument_id, broker_symbol)
        except Exception:
            pass