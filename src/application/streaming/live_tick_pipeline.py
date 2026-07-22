"""EventBus TICK → 1m bar aggregation pipeline (MD-001 increment 2).

Pure application-layer glue: normalized ticks in, completed bars out.
EventBus subscription lives in ``runtime.live_datalake_wiring`` (composition root).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from application.streaming.candle_aggregator import CandleAggregator
from domain.candles.historical import HistoricalBar, InstrumentRef
from domain.constants import DEFAULT_EXCHANGE
from domain.entities.market import MarketTick, Quote
from domain.provenance import DataProvenance

if TYPE_CHECKING:
    from domain.events.types import DomainEvent


class LiveTickBarPipeline:
    """Aggregate live ticks into OHLCV bars and invoke ``on_bar`` on each close."""

    def __init__(
        self,
        on_bar: Callable[[HistoricalBar], None],
        timeframes: Iterable[str] = ("1m",),
    ) -> None:
        self._aggregator = CandleAggregator(on_candle=on_bar, timeframes=timeframes)

    def on_tick(self, tick: MarketTick) -> None:
        self._aggregator.update(tick)

    def flush(self) -> None:
        self._aggregator.flush()


def market_tick_from_event(event: DomainEvent) -> MarketTick | None:
    """Map a TICK :class:`DomainEvent` to a normalized :class:`MarketTick`.

    Supports Dhan/Upstox publishers (``payload["quote"]``) and flat payloads.
    ponytail: exchange defaults to NSE when absent on Quote — upgrade: carry
    exchange on TICK contract or resolve via instrument registry.
    """
    payload = dict(event.payload)
    quote = payload.get("quote")
    sequence = _coerce_optional_int(payload.get("sequence"))
    session_id = str(payload.get("session_id") or "")

    if isinstance(quote, Quote):
        symbol = (quote.symbol or event.symbol or "").strip()
        if not symbol:
            return None
        exchange = str(payload.get("exchange") or DEFAULT_EXCHANGE)
        event_time = _coerce_event_time(quote.timestamp or event.timestamp)
        ltp = quote.ltp
        volume = int(quote.volume or 0)
        broker_id = str(event.source or "eventbus")
    else:
        symbol = (event.symbol or payload.get("symbol") or "").strip()
        if not symbol:
            return None
        exchange = str(payload.get("exchange") or DEFAULT_EXCHANGE)
        ltp_raw = payload.get("ltp") or payload.get("last_price")
        if ltp_raw is None:
            return None
        ltp = Decimal(str(ltp_raw))
        if ltp == 0:
            return None
        event_time = _coerce_event_time(payload.get("timestamp") or event.timestamp)
        volume = int(payload.get("volume") or 0)
        broker_id = str(event.source or "eventbus")

    return MarketTick(
        instrument=InstrumentRef(symbol=symbol, exchange=exchange),
        ltp=ltp,
        event_time=event_time,
        provenance=DataProvenance.now(broker_id, "eventbus.tick"),
        volume=volume,
        sequence=sequence,
        broker_id=broker_id,
        session_id=session_id,
    )


def _coerce_optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _coerce_event_time(ts: datetime | None) -> datetime:
    if ts is None:
        from domain.ports.time_service import get_current_clock

        return get_current_clock().now()
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts
