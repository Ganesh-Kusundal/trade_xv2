"""Live tick → candle (OHLCV) aggregator.

This module is intentionally pure and I/O-free so it can be unit-tested in
isolation and called cheaply from the stream fan-out path without blocking the
event loop.

The aggregator consumes normalized :class:`MarketTick` objects (symbol,
exchange/arrival time, last traded price, and per-tick volume) and buckets them
into calendar-aligned OHLCV candles per ``(symbol, timeframe)`` pair. A candle is
``open`` while ticks keep arriving inside its calendar window; it is ``closed``
and emitted via the supplied callback as soon as a later tick's timestamp crosses
the bucket boundary.

Boundary alignment uses the tick's resolved timestamp (``MarketTick.event_time``,
which the orchestrator sets to the exchange time when available, falling back to
arrival time). Because alignment depends only on the tick timestamp, aggregation
is fully deterministic and independent of wall-clock time.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone

from domain.candles.historical import HistoricalBar
from domain.entities.market import MarketTick

# --- timeframe parsing -------------------------------------------------------

# Common fixed timeframes. Anything not listed can be expressed with a suffix
# parser below (e.g. "30m", "2h", "1d", "1w").
_FIXED_TIMEFRAMES: Mapping[str, int] = {
    "1m": 60,
    "2m": 120,
    "5m": 300,
    "10m": 600,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "12h": 43200,
    "1d": 86400,
    "1w": 604800,
}

_SUFFIX_SECONDS: Mapping[str, int] = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}


def parse_timeframe(tf: str) -> int:
    """Return the duration of ``tf`` in seconds.

    Accepts entries from :data:`_FIXED_TIMEFRAMES` (``"1m"``, ``"5m"``,
    ``"15m"``, ``"1h"``, ...) or a ``<n><unit>`` expression where unit is one of
    ``s``, ``m``, ``h``, ``d``, ``w``.
    """
    tf = tf.strip().lower()
    if tf in _FIXED_TIMEFRAMES:
        return _FIXED_TIMEFRAMES[tf]
    if not tf:
        raise ValueError("empty timeframe")
    unit = tf[-1]
    if unit not in _SUFFIX_SECONDS:
        raise ValueError(f"unknown timeframe unit in {tf!r}")
    try:
        n = int(tf[:-1])
    except ValueError as exc:
        raise ValueError(f"invalid timeframe magnitude in {tf!r}") from exc
    if n <= 0:
        raise ValueError(f"non-positive timeframe {tf!r}")
    return n * _SUFFIX_SECONDS[unit]


# --- aggregator --------------------------------------------------------------


class CandleAggregator:
    """Aggregate normalized ticks into calendar-aligned OHLCV candles.

    Usage::

        agg = CandleAggregator(on_candle=my_callback, timeframes=("1m", "5m"))
        agg.update(tick)  # called per normalized tick

    ``on_candle`` is invoked synchronously with each completed :class:`HistoricalBar`.
    The aggregator holds bounded per-``(symbol, timeframe)`` state (a single open
    bucket each), so steady-state memory is ``O(symbols * timeframes)``.
    """

    def __init__(
        self,
        on_candle: Callable[[HistoricalBar], None],
        timeframes: Iterable[str] = ("1m", "5m", "15m", "1h"),
    ) -> None:
        if on_candle is None:
            raise ValueError("on_candle callback is required")
        self._on_candle = on_candle
        self._timeframes: tuple[str, ...] = tuple(dict.fromkeys(timeframes))
        if not self._timeframes:
            raise ValueError("at least one timeframe is required")
        # Validate durations eagerly so misconfiguration fails fast.
        self._durations = {tf: parse_timeframe(tf) for tf in self._timeframes}

        # (symbol_key, timeframe) -> open bucket state.
        self._buckets: dict[tuple[str, str], dict] = {}

    # -- public API -----------------------------------------------------------

    def update(self, tick: MarketTick) -> None:
        """Feed one normalized tick into the aggregator.

        Late ticks that fall strictly before an already-closed bucket are
        discarded (their window has already been emitted and cannot be
        reconstructed). Ticks inside the currently open bucket are merged.
        """
        ts = tick.event_time
        if ts.tzinfo is None:
            # Defensive: normalize naive timestamps to UTC. The orchestrator
            # always emits timezone-aware times, but this keeps the aggregator
            # robust to hand-built ticks in tests.
            ts = ts.replace(tzinfo=timezone.utc)
        ts_epoch = ts.timestamp()

        symbol = tick.instrument.symbol
        exchange = tick.instrument.exchange
        symbol_key = f"{symbol}:{exchange}"
        price = float(tick.ltp)
        vol = float(tick.volume or 0)

        for tf in self._timeframes:
            dur = self._durations[tf]
            bucket_start_epoch = int(ts_epoch // dur) * dur
            bucket_start = datetime.fromtimestamp(bucket_start_epoch, tz=timezone.utc)

            key = (symbol_key, tf)
            cur = self._buckets.get(key)

            if cur is not None and cur["open_epoch"] < bucket_start_epoch:
                # Boundary crossed: close the open bucket, then start a new one.
                self._emit(cur, tf, dur)
                cur = None
            elif cur is not None and cur["open_epoch"] > bucket_start_epoch:
                # Late tick for an already-closed window — ignore.
                continue

            if cur is None:
                self._buckets[key] = {
                    "symbol": symbol,
                    "exchange": exchange,
                    "open_epoch": bucket_start_epoch,
                    "open_time": bucket_start,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": vol,
                    "tick_count": 1,
                }
            else:
                if price > cur["high"]:
                    cur["high"] = price
                if price < cur["low"]:
                    cur["low"] = price
                cur["close"] = price
                cur["volume"] += vol
                cur["tick_count"] += 1

    def flush(self) -> None:
        """Emit all currently open buckets as completed candles.

        Useful on shutdown to avoid losing the partial candle for an interval
        that has not yet received a boundary-crossing tick.
        """
        for tf in self._timeframes:
            dur = self._durations[tf]
            for key in [k for k in self._buckets if k[1] == tf]:
                self._emit(self._buckets.pop(key), tf, dur)

    def open_symbols(self) -> set[str]:
        """Return the set of ``symbol:exchange`` keys with an open bucket."""
        return {k[0] for k in self._buckets}

    # -- internals ------------------------------------------------------------

    def _emit(self, bucket: dict, tf: str, dur: int) -> None:
        candle = HistoricalBar.from_live_bucket(
            symbol=bucket["symbol"],
            exchange=bucket["exchange"],
            timeframe=tf,
            open_time=bucket["open_time"],
            close_time=datetime.fromtimestamp(bucket["open_epoch"] + dur, tz=timezone.utc),
            open=bucket["open"],
            high=bucket["high"],
            low=bucket["low"],
            close=bucket["close"],
            volume=bucket["volume"],
            tick_count=bucket["tick_count"],
        )
        self._on_candle(candle)
