"""Live tick → candle (OHLCV) aggregator.

Buckets are aligned to IST wall-clock boundaries (exchange session timezone),
not raw UTC epoch floors, so 1m bars open at :00 IST (e.g. 09:15 IST) rather
than at UTC minute boundaries.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from decimal import Decimal

from domain.candles.historical import HistoricalBar
from domain.constants.market import IST
from domain.entities.market import MarketTick

# --- timeframe parsing -------------------------------------------------------

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
    """Return the duration of ``tf`` in seconds."""
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


def _bucket_bounds(ts: datetime, dur: int) -> tuple[int, datetime]:
    """Return (open_epoch, open_time) aligned to IST calendar buckets."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ist_epoch = ts.astimezone(IST).timestamp()
    open_epoch = int(ist_epoch // dur) * dur
    open_time = datetime.fromtimestamp(open_epoch, tz=IST)
    return open_epoch, open_time


class CandleAggregator:
    """Aggregate normalized ticks into calendar-aligned OHLCV candles."""

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
        self._durations = {tf: parse_timeframe(tf) for tf in self._timeframes}
        self._buckets: dict[tuple[str, str], dict] = {}

    def update(self, tick: MarketTick, *, is_correction: bool = False) -> None:
        """Feed one normalized tick into the aggregator.

        When ``is_correction`` is True and the tick targets an already-closed
        bucket, the open bucket state is updated and the bar re-emitted instead
        of being silently dropped.
        """
        ts = tick.event_time
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_epoch = ts.astimezone(IST).timestamp()

        symbol = tick.instrument.symbol
        exchange = tick.instrument.exchange
        symbol_key = f"{symbol}:{exchange}"
        price = float(tick.ltp)
        vol = float(tick.volume or 0)

        for tf in self._timeframes:
            dur = self._durations[tf]
            bucket_start_epoch, bucket_start = _bucket_bounds(ts, dur)

            key = (symbol_key, tf)
            cur = self._buckets.get(key)

            if cur is not None and cur["open_epoch"] < bucket_start_epoch:
                self._emit(cur, tf, dur)
                cur = None
            elif (
                cur is not None
                and cur["open_epoch"] > bucket_start_epoch
                and not is_correction
            ):
                continue
            elif (
                cur is not None
                and cur["open_epoch"] > bucket_start_epoch
                and is_correction
            ):
                cur = None

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
                if is_correction:
                    self._emit(self._buckets[key], tf, dur)
            else:
                if price > cur["high"]:
                    cur["high"] = price
                if price < cur["low"]:
                    cur["low"] = price
                cur["close"] = price
                cur["volume"] += vol
                cur["tick_count"] += 1
                if is_correction:
                    self._emit(cur, tf, dur)

    def apply_reconciled_bar(self, bar: HistoricalBar) -> None:
        """Apply a gap-filled historical bar through the live bar callback."""
        self._on_candle(bar)

    def flush(self) -> None:
        """Emit all currently open buckets as completed candles."""
        for tf in self._timeframes:
            dur = self._durations[tf]
            for key in [k for k in self._buckets if k[1] == tf]:
                self._emit(self._buckets.pop(key), tf, dur)

    def open_symbols(self) -> set[str]:
        """Return the set of ``symbol:exchange`` keys with an open bucket."""
        return {k[0] for k in self._buckets}

    def _emit(self, bucket: dict, tf: str, dur: int) -> None:
        candle = HistoricalBar.from_live_bucket(
            symbol=bucket["symbol"],
            exchange=bucket["exchange"],
            timeframe=tf,
            open_time=bucket["open_time"],
            close_time=datetime.fromtimestamp(bucket["open_epoch"] + dur, tz=IST),
            open=bucket["open"],
            high=bucket["high"],
            low=bucket["low"],
            close=bucket["close"],
            volume=bucket["volume"],
            tick_count=bucket["tick_count"],
        )
        self._on_candle(candle)
