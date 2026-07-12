"""Bar iteration and window building for paper trading.

Extracted from ``analytics.paper.engine.PaperTradingEngine``. Builds sliding
windows of OHLCV bars and runs the feature pipeline. The feature pipeline is an
optional dependency (defaults to an empty ``FeaturePipeline``).
"""

from __future__ import annotations

import logging
from collections.abc import Generator

import pandas as pd

from analytics.paper.models import PaperConfig, PaperSession
from analytics.pipeline.errors import FeaturePipelineError
from analytics.pipeline.pipeline import FeaturePipeline
from domain.candles.historical import HistoricalBar

logger = logging.getLogger(__name__)


class BarWindowManager:
    """Iterate bars from a DataFrame and build/feature sliding windows.

    Parameters
    ----------
    pipeline:
        FeaturePipeline for computing indicators on each window. Defaults to an
        empty ``FeaturePipeline`` when ``None``.
    """

    def __init__(self, pipeline: FeaturePipeline | None = None) -> None:
        self._pipeline = pipeline or FeaturePipeline()

    @staticmethod
    def iter_bars(
        df: pd.DataFrame, symbol: str, ts_col: str
    ) -> Generator[HistoricalBar, None, None]:
        """Yield :class:`HistoricalBar` instances from a DataFrame in row order.

        Extracted from the old ``_bar_generator`` closures in ``_run_single``
        and ``_run_multi_symbol`` to avoid re-defining the closure on every
        iteration of the caller's loop.
        """
        for idx in range(len(df)):
            row = df.iloc[idx]
            sym = str(row["symbol"]) if "symbol" in df.columns else symbol
            yield HistoricalBar.from_replay(
                symbol=sym,
                timestamp=row[ts_col],
                open=float(row.get("open", 0)),
                high=float(row.get("high", 0)),
                low=float(row.get("low", 0)),
                close=float(row.get("close", 0)),
                volume=float(row.get("volume", 0)),
            )

    @staticmethod
    def build_window(window: list[dict], window_size: int) -> pd.DataFrame:
        """Build a DataFrame from the window, optionally limiting size."""
        if window_size > 0:
            window = window[-window_size:]
        return pd.DataFrame(window)

    def run_features(
        self, window_df: pd.DataFrame, session: PaperSession, config: PaperConfig
    ) -> pd.DataFrame | None:
        """Run feature pipeline; return None on fail-closed skip (no neutral fallback)."""
        self._pipeline.fail_closed = config.fail_closed_features
        try:
            return self._pipeline.run(window_df)
        except FeaturePipelineError as exc:
            logger.warning(
                "Feature pipeline fail-closed at bar %d: %s",
                session.bar_count,
                exc,
            )
            return None
