"""InstrumentHistory — callable history facade attached to an Instrument.

Preserves ``instrument.history(timeframe=..., days=...)`` via ``__call__``
while adding download/refresh/resample/cache (OBJECT_MODEL KD-3).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain.candles.historical import HistoricalSeries, InstrumentRef

if TYPE_CHECKING:
    from domain.instruments.instrument import Instrument


class InstrumentHistory:
    """Attached history control surface for a single instrument.

    Cache policy
    ------------
    - ``_downloaded``: last series from provider download/refresh only.
    - ``_view``: optional last transform (resample); does **not** replace
      ``_downloaded``.
    - ``series`` returns ``_view or _downloaded``.
    - ``download`` / ``refresh`` / ``__call__`` set ``_downloaded`` and clear
      ``_view``.
    - ``resample`` sets ``_view`` only.
    """

    def __init__(self, owner: Instrument) -> None:
        self._owner = owner
        self._downloaded: HistoricalSeries | None = None
        self._view: HistoricalSeries | None = None
        self._last_params: dict[str, Any] = {
            "timeframe": "1D",
            "days": 120,
            "start": None,
            "end": None,
        }

    def __call__(
        self,
        *,
        timeframe: str = "1D",
        days: int = 120,
        start: str | None = None,
        end: str | None = None,
    ) -> HistoricalSeries:
        """Fetch history (same kwargs as the former ``Instrument.history`` method)."""
        return self.download(timeframe=timeframe, days=days, start=start, end=end)

    def download(
        self,
        *,
        timeframe: str = "1D",
        days: int = 120,
        start: str | None = None,
        end: str | None = None,
    ) -> HistoricalSeries:
        """Fetch from provider and replace download cache."""
        from domain.instruments.timeframes import normalize_timeframe

        timeframe = normalize_timeframe(timeframe)
        self._last_params = {
            "timeframe": timeframe,
            "days": days,
            "start": start,
            "end": end,
        }
        series = self._fetch(timeframe=timeframe, days=days, start=start, end=end)
        if series is None:
            series = HistoricalSeries(
                bars=[],
                coverage=None,
                instrument=InstrumentRef(symbol=self._owner.symbol, exchange=self._owner.exchange),
                timeframe=timeframe,
            )
        self._downloaded = series
        self._view = None
        return series

    def refresh(
        self,
        *,
        timeframe: str | None = None,
        days: int | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> HistoricalSeries:
        """Re-fetch using last download params (overridable)."""
        p = dict(self._last_params)
        if timeframe is not None:
            p["timeframe"] = timeframe
        if days is not None:
            p["days"] = days
        if start is not None:
            p["start"] = start
        if end is not None:
            p["end"] = end
        return self.download(**p)

    def _fetch(
        self,
        *,
        timeframe: str,
        days: int,
        start: str | None,
        end: str | None,
    ) -> HistoricalSeries:
        owner = self._owner
        provider = owner._resolve_provider()
        try:
            series = provider.get_history_series(
                owner.id,
                timeframe=timeframe,
                lookback_days=days,
                from_date=start,
                to_date=end,
            )
            if series is not None and getattr(series, "bar_count", 0) > 0:
                return series
        except (AttributeError, NotImplementedError, TypeError):
            pass
        try:
            bars = provider.get_history(
                owner.id,
                timeframe=timeframe,
                lookback_days=days,
                from_date=start,
                to_date=end,
            )
            if isinstance(bars, HistoricalSeries):
                return bars
            if isinstance(bars, list):
                return HistoricalSeries(
                    bars=bars,
                    coverage=None,
                    instrument=InstrumentRef(symbol=owner.symbol, exchange=owner.exchange),
                    timeframe=timeframe,
                )
            return HistoricalSeries.from_broker_df(
                bars,
                InstrumentRef(symbol=owner.symbol, exchange=owner.exchange),
                timeframe,
                broker_id=getattr(provider, "name", "unknown"),
                request_id="legacy_dataframe_fallback",
            )
        except Exception as exc:
            # ponytail: only swallow non-provider errors. Provider/broker
            # failures (entitlement, auth, network) must propagate so the CLI
            # and callers can surface them — an empty series hides real bugs.
            if isinstance(exc, AttributeError | NotImplementedError | TypeError):
                return HistoricalSeries(
                    bars=[],
                    coverage=None,
                    instrument=InstrumentRef(symbol=owner.symbol, exchange=owner.exchange),
                    timeframe=timeframe,
                )
            raise

    @property
    def series(self) -> HistoricalSeries | None:
        """Last transform view, else last download."""
        if self._view is not None:
            return self._view
        return self._downloaded

    @property
    def downloaded(self) -> HistoricalSeries | None:
        return self._downloaded

    def resample(self, target_timeframe: str) -> HistoricalSeries:
        """Resample cached series; does not overwrite download cache."""
        base = self.series
        if base is None:
            from domain.errors import NotConfiguredError

            raise NotConfiguredError("No history loaded; call download() or history(...) first")
        out = base.resample(target_timeframe)
        self._view = out
        return out

    def indicators(self):
        """Indicator accessor on the current series (loads download if needed)."""
        base = self.series
        if base is None:
            base = self.download()
        return base.indicators()

    def to_dataframe(self):
        """Export current series as a pandas DataFrame."""
        base = self.series
        if base is None:
            base = self.download()
        return base.to_dataframe()

    @property
    def bar_count(self) -> int:
        s = self.series
        return s.bar_count if s is not None else 0
