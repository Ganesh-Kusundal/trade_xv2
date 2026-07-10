"""Session-gap reconciler for live -> historical data continuity.

This goes *beyond* the reconnect-only M5 backfill (wired in
``application.composer.factory._build_default_backfill_callback``). The M5
backfill only fills the gap reported by a single reconnect event. This
reconciler performs a *session-level* sweep: for each subscribed instrument it
determines the time range that is missing from local data — between the last
locally-known tick/candle time and ``now``, *minus* what a recent reconnect
backfill already covered — and fills it by requesting historical bars from the
existing ``HistoricalDataCoordinator`` and publishing them through the normal
tick/candle path (so they are persisted).

Design constraints:

* **Bounded** — caps the total gap span per instrument (``max_gap_span``) and
  the number of instruments processed per run (``max_instruments``) so a long
  disconnect can never trigger an unbounded fetch.
* **No historical source -> skip** — if the coordinator returns no bars for an
  instrument (no eligible source / nothing to fill), that instrument is simply
  skipped; no empty publish, no crash.
* **No coordinator -> no-op** — when no ``HistoricalDataCoordinator`` is
  configured the reconciler returns ``[]`` immediately and never raises.
* **Reuses existing plumbing** — fetching delegates to
  ``factory._fetch_gap_bars`` (the same path the M5 backfill uses) rather than
  inventing a new fetch route, so bar-normalization and date-granularity
  handling stay consistent.

The reconciler is intentionally decoupled from any specific publish sink: the
caller supplies ``fill_callback(key, bars)`` (the factory wires a best-effort
sink that pushes through the normal stream path). This keeps the reconciler
purely about detection + fetch + dispatch.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from typing import Any

from application.composer.factory import _fetch_gap_bars, _split_instrument_key
from infrastructure.time.clock import time_service


logger = logging.getLogger(__name__)

# Bounds: a single reconcile run will not request more than this span per
# instrument, and will not process more instruments than this cap. These keep
# the reconciler cheap and bounded even after a long disconnect.
DEFAULT_MAX_GAP_SPAN = timedelta(days=7)
DEFAULT_MAX_INSTRUMENTS = 50
DEFAULT_TIMEFRAME = "1m"


class GapReconciler:
    """Detect and fill session gaps for a set of subscribed instruments.

    Parameters
    ----------
    historical_coordinator
        The existing ``HistoricalDataCoordinator`` (or a compatible fake in
        tests). ``None`` makes every ``reconcile`` call a no-op.
    timeframe
        Candle interval used when fetching the missing bars.
    max_gap_span
        Hard cap on the time span fetched per instrument in a single run.
    max_instruments
        Hard cap on how many subscribed instruments are processed per run.
    last_known_fn
        ``key -> datetime | None``. Returns the last locally-known sample time
        for an instrument, or ``None`` if unknown (in which case the gap is
        bounded to ``[now - max_gap_span, now]``).
    fill_callback
        ``(key, list[dict]) -> None`` invoked with the fetched gap bars so the
        caller can publish them through the normal tick/candle path.
    """

    def __init__(
        self,
        historical_coordinator: Any | None,
        *,
        timeframe: str = DEFAULT_TIMEFRAME,
        max_gap_span: timedelta = DEFAULT_MAX_GAP_SPAN,
        max_instruments: int = DEFAULT_MAX_INSTRUMENTS,
        last_known_fn: Callable[[str], datetime | None] | None = None,
        fill_callback: Callable[[str, list[dict]], None] | None = None,
    ) -> None:
        self._coordinator = historical_coordinator
        self._timeframe = timeframe
        self._max_gap_span = max_gap_span
        self._max_instruments = max_instruments
        self._last_known_fn = last_known_fn or (lambda key: None)
        self._fill_callback = fill_callback

    def reconcile(
        self,
        subscribed: Iterable[str],
        *,
        now: datetime | None = None,
        already_covered_to: dict[str, datetime] | None = None,
    ) -> list[dict]:
        """Detect and fill session gaps for the subscribed instruments.

        Parameters
        ----------
        subscribed
            Iterable of instrument keys (e.g. ``"RELIANCE:NSE"`` or
            ``"NSE_EQ|RELIANCE"``) understood by
            ``factory._split_instrument_key``.
        now
            Reference "current" time. Defaults to ``time_service.now()`` (UTC).
        already_covered_to
            Optional ``{key: datetime}`` mapping of ranges a recent reconnect
            backfill already filled, which are subtracted from the gap so we do
            not re-fetch what was just backfilled.

        Returns
        -------
        list[dict]
            One result dict per successfully filled instrument (for
            observability). Empty when there is no coordinator, no subscribed
            instruments, or nothing to fill.
        """
        if self._coordinator is None:
            logger.debug("gap_reconcile.skipped_no_coordinator")
            return []
        subscribed = list(subscribed or [])
        if not subscribed:
            return []

        now = now or time_service.now()

        already = already_covered_to or {}

        results: list[dict] = []
        # Bound the number of instruments processed per run.
        for key in subscribed[: self._max_instruments]:
            key = str(key)
            try:
                result = self._reconcile_one(key, now, already.get(key))
                if result is not None:
                    results.append(result)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "gap_reconcile.failed",
                    extra={"key": key, "error": str(exc)},
                )
        return results

    def _reconcile_one(
        self,
        key: str,
        now: datetime,
        already_covered_to: datetime | None,
    ) -> dict | None:
        symbol, exchange = _split_instrument_key(key)
        if not symbol:
            return None

        start = self._gap_start(key, now, already_covered_to)
        end = now

        # Final safety clamp: never exceed the per-run span bound.
        if end - start > self._max_gap_span:
            start = end - self._max_gap_span
        if start >= end:
            # No gap to fill (already covered or last-known == now).
            return None

        bars = _fetch_gap_bars(self._coordinator, symbol, exchange, start, end)
        if not bars:
            # No historical source returned data -> skip (do not publish).
            logger.debug("gap_reconcile.no_bars", extra={"key": key})
            return None

        if self._fill_callback is not None:
            self._fill_callback(key, bars)

        return {
            "key": key,
            "symbol": symbol,
            "exchange": exchange,
            "from": start,
            "to": end,
            "bar_count": len(bars),
        }

    def _gap_start(
        self,
        key: str,
        now: datetime,
        already_covered_to: datetime | None,
    ) -> datetime:
        """Compute the gap start time, applying last-known and already-covered.

        The gap begins just after the last locally-known sample (or
        ``now - max_gap_span`` when unknown), then is advanced past anything a
        recent reconnect backfill already covered.
        """
        last_known = self._last_known_fn(key)
        if last_known is None:
            start = now - self._max_gap_span
        else:
            start = last_known

        if already_covered_to is not None and already_covered_to > start:
            start = already_covered_to
        return start
