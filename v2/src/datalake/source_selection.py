"""Concrete SourceSelectionPolicy — local datalake first, then remote broker."""

from __future__ import annotations

from datalake.catalog import DataCatalog
from domain.policies.source_selection import DataSourceKind
from domain.value_objects import InstrumentId, TimeFrame


class SourceSelectionPolicy:
    """Prefer DATALAKE when local bars exist; else BROKER_HISTORICAL."""

    def __init__(self, catalog: DataCatalog) -> None:
        self._catalog = catalog

    def select(self, instrument_id: InstrumentId, timeframe: TimeFrame) -> DataSourceKind:
        del timeframe  # Phase 5: symbol-level presence only
        symbol = instrument_id.value
        # Accept both "NSE:RELIANCE" and "RELIANCE" lake keys
        bare = symbol.split(":", 1)[-1]
        if self._catalog.has_bars(symbol) or self._catalog.has_bars(bare):
            return DataSourceKind.DATALAKE
        return DataSourceKind.BROKER_HISTORICAL
