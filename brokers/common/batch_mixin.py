"""BatchFetchMixin — shared parallel-fetch implementation for gateways.

Gateways that inherit this mixin get ltp_batch, quote_batch, and
history_batch for free, as long as they implement the single-item
methods ltp(), quote(), and history().

Brokers with native batch APIs (e.g., Dhan's get_batch_ltp) should
override these methods for better performance.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class BatchFetchMixin:
    """Mixin providing parallel batch-fetch methods via ThreadPoolExecutor.

    Subclasses must implement:
    - ltp(symbol, exchange) -> Decimal
    - quote(symbol, exchange) -> Any
    - history(symbol, exchange, timeframe, lookback_days) -> pd.DataFrame
    """

    _batch_max_workers: int = 5

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        results: dict[str, Decimal] = {}
        with ThreadPoolExecutor(max_workers=self._batch_max_workers) as executor:
            futures = {
                executor.submit(self.ltp, sym, exchange): sym  # type: ignore[attr-defined]
                for sym in symbols
            }
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    results[sym] = future.result()
                except Exception as exc:
                    logger.debug("ltp_batch_failed: %s: %s", sym, exc)
                    results[sym] = Decimal("0")
        return results

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Any]:
        results: dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=self._batch_max_workers) as executor:
            futures = {
                executor.submit(self.quote, sym, exchange): sym  # type: ignore[attr-defined]
                for sym in symbols
            }
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    results[sym] = future.result()
                except Exception as exc:
                    logger.debug("quote_batch_failed: %s: %s", sym, exc)
        return results

    def history_batch(
        self,
        symbols: list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
    ) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        with ThreadPoolExecutor(max_workers=self._batch_max_workers) as executor:
            futures = {
                executor.submit(self.history, sym, exchange, timeframe, lookback_days): sym  # type: ignore[attr-defined]
                for sym in symbols
            }
            for future in as_completed(futures):
                try:
                    df = future.result()
                    if not df.empty:
                        frames.append(df)
                except Exception as exc:
                    logger.debug("batch_fetch_future_failed: %s", exc)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
