"""TickRouter — message normalization, dedup, and fan-out to consumers.

Owns the hot path for every frame arriving from a broker transport:
  1. Normalize raw frame → ``MarketTick`` or ``OrderUpdate``
  2. Dedup (bounded time-windowed cache)
  3. Fan-out to all registered consumers for the session
  4. Update session freshness

Also owns consumer health notifications.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from domain.candles.historical import InstrumentRef
from domain.ports.time_service import get_current_clock
from domain.stream_health import FreshnessState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dedup constants  (moved from orchestrator)
# ---------------------------------------------------------------------------
_STREAM_DEDUP_WINDOW_S = 2.0
_STREAM_DEDUP_MAX_ENTRIES = 4096
_STREAM_DEDUP_COARSE_BUCKET_S = 1.0


def _parse_exchange_time(ts_raw, now: datetime) -> datetime:
    """Resolve an exchange timestamp carried by a quote, else fall back to *now*."""
    if ts_raw is None:
        return now
    if isinstance(ts_raw, datetime):
        return ts_raw if ts_raw.tzinfo else ts_raw.replace(tzinfo=now.tzinfo)
    try:
        if isinstance(ts_raw, int | float):
            if ts_raw <= 0:
                return now
            if ts_raw > 1e11:
                return datetime.fromtimestamp(ts_raw / 1000, tz=now.tzinfo)
            return datetime.fromtimestamp(ts_raw, tz=now.tzinfo)
        if isinstance(ts_raw, str) and ts_raw.strip():
            return datetime.fromisoformat(ts_raw)
    except (ValueError, OSError, OverflowError):
        return now
    return now


class TickRouter:
    """Normalize, deduplicate, and deliver stream messages to consumers.

    Parameters
    ----------
    subscriptions : dict[str, _ActiveSubscription]
        Shared reference — orchestrator owns the dict, router reads it.
    sessions : dict[str, StreamSession]
        Shared reference — router updates freshness on sessions.
    lock : asyncio.Lock
        Shared lock for thread-safe access to shared dicts.
    candle_aggregator : CandleAggregator | None
        Optional live candle aggregator fed every normalized tick.
    """

    def __init__(
        self,
        subscriptions,
        sessions,
        lock: asyncio.Lock,
        candle_aggregator=None,
        tick_hook=None,
    ) -> None:
        self._subscriptions = subscriptions
        self._sessions = sessions
        self._lock = lock
        self._candle_aggregator = candle_aggregator
        self._tick_hook = tick_hook
        # Dedup cache: (instrument_key, event_time, sequence) -> wall-clock seen.
        self._dedup_seen: dict[tuple, float] = {}

    # ------------------------------------------------------------------
    # Fan-out
    # ------------------------------------------------------------------

    async def deliver_tick(self, session_id: str, tick) -> None:
        """Deliver a market tick to all consumers of the session."""
        subs = [s for s in self._subscriptions.values() if s.session_id == session_id]
        for sub in subs:
            try:
                await asyncio.wait_for(
                    sub.consumer.on_market_tick(tick),
                    timeout=1.0,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "stream.consumer.slow",
                    extra={
                        "consumer_id": sub.consumer.consumer_id(),
                        "session_id": session_id,
                    },
                )
            except Exception:
                logger.exception(
                    "stream.consumer.error",
                    extra={"consumer_id": sub.consumer.consumer_id()},
                )

        # Optional live candle aggregation
        if self._candle_aggregator is not None:
            try:
                self._candle_aggregator.update(tick)
            except Exception:
                logger.exception("stream.candle_aggregator.error")

        if self._tick_hook is not None:
            try:
                self._tick_hook(tick)
            except Exception:
                logger.exception("stream.tick_hook.error")

        # Update freshness on valid tick
        session = self._sessions.get(session_id)
        if session:
            now = get_current_clock().now()
            session.record_message(now)
            prev = session.health.freshness
            session.update_freshness(FreshnessState.FRESH, at=now)
            if prev != FreshnessState.FRESH:
                await self.notify_health_change(session_id, session.health)

    async def deliver_order_update(self, session_id: str, update) -> None:
        """Deliver an order update to all consumers of the session."""
        subs = [s for s in self._subscriptions.values() if s.session_id == session_id]
        for sub in subs:
            try:
                await sub.consumer.on_order_update(update)
            except Exception:
                logger.exception(
                    "stream.consumer.order_update.error",
                    extra={"consumer_id": sub.consumer.consumer_id()},
                )

    # ------------------------------------------------------------------
    # Dedup
    # ------------------------------------------------------------------

    def dedup_drop(
        self,
        instrument_key: str,
        event_time: datetime,
        sequence: int | None,
        ltp: float | None = None,
        trusted_time: bool = False,
    ) -> bool:
        """Drop market ticks that repeat within the dedup window.

        Returns ``True`` when the tick should be *dropped* (already seen).
        """
        now_ts = get_current_clock().now().timestamp()
        primary_key = (instrument_key, event_time, sequence)
        if primary_key in self._dedup_seen:
            logger.debug(
                "stream.tick.dedup",
                extra={"instrument": instrument_key, "event_time": event_time.isoformat()},
            )
            return True

        fallback_key = None
        if not trusted_time and ltp is not None:
            bucket = int(now_ts // _STREAM_DEDUP_COARSE_BUCKET_S)
            fallback_key = (instrument_key, ltp, bucket)
            if fallback_key in self._dedup_seen:
                logger.debug(
                    "stream.tick.dedup.dhan_fallback",
                    extra={"instrument": instrument_key, "ltp": ltp, "bucket": bucket},
                )
                return True

        if len(self._dedup_seen) >= _STREAM_DEDUP_MAX_ENTRIES:
            cutoff = now_ts - _STREAM_DEDUP_WINDOW_S
            self._dedup_seen = {k: t for k, t in self._dedup_seen.items() if t > cutoff}
        self._dedup_seen[primary_key] = now_ts
        if fallback_key is not None:
            self._dedup_seen[fallback_key] = now_ts
        return False

    # ------------------------------------------------------------------
    # Frame handling
    # ------------------------------------------------------------------

    async def handle_frame(self, session_id: str, frame, stream_kind: str) -> None:
        """Normalize a raw broker frame and deliver to consumers."""
        session = self._sessions.get(session_id)
        if session is None:
            return

        now = get_current_clock().now()
        session.record_message(now)

        if stream_kind == "market":
            if isinstance(frame, dict):
                symbol = frame.get("symbol") or frame.get("trading_symbol") or ""
                if symbol:
                    exchange = frame.get("exchange") or "NSE"
                    event_time = _parse_exchange_time(
                        frame.get("timestamp") or frame.get("exchange_timestamp"), now
                    )
                    sequence = frame.get("sequence")
                    trusted_time = frame.get("exchange_timestamp") is not None
                    ltp = frame.get("ltp") or frame.get("last_price") or 0
                    if self.dedup_drop(
                        f"{symbol}:{exchange}",
                        event_time,
                        sequence,
                        ltp=ltp,
                        trusted_time=trusted_time,
                    ):
                        return
            tick = self._normalize_tick(frame, session_id, session.broker_id, now)
            if tick is not None:
                await self.deliver_tick(session_id, tick)
        else:
            update = self._normalize_order_update(frame, session_id, session.broker_id, now)
            if update is not None:
                await self.deliver_order_update(session_id, update)

    # ------------------------------------------------------------------
    # Normalization (stateless / static)
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_tick(frame, session_id: str, broker_id: str, now: datetime):
        """Map a raw broker frame to a domain ``MarketTick``, or ``None``."""
        from decimal import Decimal

        from domain.entities.market import MarketTick
        from domain.provenance import DataProvenance

        if not isinstance(frame, dict):
            return None
        symbol = frame.get("symbol") or frame.get("trading_symbol") or ""
        exchange = frame.get("exchange") or "NSE"
        if not symbol:
            return None
        event_time = _parse_exchange_time(
            frame.get("timestamp") or frame.get("exchange_timestamp"), now
        )

        def _dec(key: str) -> Decimal | None:
            if key not in frame or frame[key] is None:
                return None
            return Decimal(str(frame[key]))

        ltp_raw = frame.get("ltp") or frame.get("last_price") or 0
        from brokers.common.quote_normalize import tick_volume_from_frame

        volume = tick_volume_from_frame(frame, str(symbol), str(exchange))
        return MarketTick(
            instrument=InstrumentRef(symbol=symbol, exchange=exchange),
            ltp=Decimal(str(ltp_raw)),
            event_time=event_time,
            provenance=DataProvenance.now(broker_id, "stream"),
            volume=volume,
            bid=_dec("bid"),
            ask=_dec("ask"),
            broker_id=broker_id,
            session_id=session_id,
            sequence=frame.get("sequence"),
            open=_dec("open"),
            high=_dec("high"),
            low=_dec("low"),
        )

    @staticmethod
    def _normalize_order_update(frame, session_id: str, broker_id: str, now: datetime):
        """Map a raw broker frame to an ``OrderUpdate``, or ``None``."""
        from application.streaming.orchestrator import OrderUpdate

        if not isinstance(frame, dict):
            return None
        return OrderUpdate(
            broker_id=broker_id,
            session_id=session_id,
            event_time=now,
            order_id=str(frame.get("order_id") or ""),
            status=str(frame.get("status") or ""),
            filled_qty=int(frame.get("filled_qty") or 0),
            avg_price=float(frame.get("avg_price") or 0),
            raw=frame,
        )

    # ------------------------------------------------------------------
    # Health notifications
    # ------------------------------------------------------------------

    async def notify_health_change(self, session_id: str, health) -> None:
        """Notify all consumers of a session about a health change."""
        subs = [s for s in self._subscriptions.values() if s.session_id == session_id]
        for sub in subs:
            notify = getattr(sub.consumer, "on_stream_health_change", None)
            if callable(notify):
                try:
                    await notify(session_id, health)
                except Exception:
                    logger.exception(
                        "stream.consumer.health_change.error",
                        extra={"consumer_id": sub.consumer.consumer_id()},
                    )
