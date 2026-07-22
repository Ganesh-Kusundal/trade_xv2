"""Contract historical fetch port — datalake sync boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    import pandas as pd

    from domain.candles.contract_historical import ContractHistoricalQuery


class ContractHistoricalFetchPort(Protocol):
    """Fetch exact-contract OHLCV for one query."""

    def __call__(
        self,
        query: "ContractHistoricalQuery",
    ) -> tuple["pd.DataFrame | Any", Any]: ...
