"""Historical routing lane — eligibility dimensions for broker selection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from domain.historical.contract_state import ContractState
from domain.instruments.asset_kind import AssetKind


@dataclass(frozen=True, slots=True)
class HistoricalRouteLane:
    """Dimensions used to decide which broker can serve a historical request."""

    asset_kind: AssetKind
    exchange: str
    contract_state: ContractState
    timeframe: str
    lookback_days: int
    underlying: str | None = None
    rolling_index_options: bool = False  # Dhan /charts/rollingoption lane

    def endpoint_class(self) -> str:
        if self.rolling_index_options:
            return "options_historical"
        return "historical"
