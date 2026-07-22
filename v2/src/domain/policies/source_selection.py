"""Source selection policy port."""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from domain.value_objects import InstrumentId, TimeFrame


class DataSourceKind(Enum):
    DATALAKE = "DATALAKE"
    BROKER_HISTORICAL = "BROKER_HISTORICAL"
    FEDERATED = "FEDERATED"


@runtime_checkable
class SourceSelectionPolicy(Protocol):
    def select(self, instrument_id: InstrumentId, timeframe: TimeFrame) -> DataSourceKind: ...
