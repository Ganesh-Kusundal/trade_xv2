"""Options historical fetch port — contract between datalake sync and broker federation."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    import pandas as pd


class OptionsHistoricalFetchPort(Protocol):
    """Fetch rolling options OHLCV for one lake partition over a date range.

    Implemented by ``application.data.options_sync_fetch_strategy.build_federated_options_fetch_fn``
    (production) or an injected test double. Passed into
    :func:`datalake.ingestion.sync_options.sync_options`.
    """

    def __call__(
        self,
        underlying: str,
        expiry_kind: str,
        expiry_code: int,
        from_date: date,
        to_date: date,
    ) -> "pd.DataFrame | Any": ...
