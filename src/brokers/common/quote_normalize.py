"""Shared quote normalization for broker DataProviders."""

from __future__ import annotations

import threading
from datetime import datetime
from decimal import Decimal
from typing import Any

from domain.candles.historical import InstrumentRef
from domain.entities.market import QuoteSnapshot
from domain.instruments.instrument_id import InstrumentId
from domain.ports.time_service import get_current_clock
from domain.provenance import DataProvenance, ProvenanceConfidence, SourceIdentity


class CumulativeVolumeTracker:
    """Convert cumulative day volume (vtt) to per-tick deltas.

    Upstox FULL/option frames expose ``vtt`` (volume traded today). LTPC
    frames expose ``ltq`` (last traded qty) and are already incremental.
    ponytail: in-memory per-process tracker; upgrade: session-scoped store.
    """

    def __init__(self) -> None:
        self._last: dict[str, int] = {}
        self._lock = threading.Lock()

    def tick_volume(
        self,
        key: str,
        reported: int,
        *,
        cumulative: bool,
    ) -> int:
        if reported <= 0:
            return 0
        if not cumulative:
            return reported
        with self._lock:
            prev = self._last.get(key, 0)
            if reported < prev:
                prev = 0
            delta = reported - prev
            self._last[key] = reported
            return max(delta, 0)


_VOLUME_TRACKER = CumulativeVolumeTracker()


def tick_volume_from_frame(frame: dict[str, Any], symbol: str, exchange: str) -> int:
    """Resolve incremental tick volume from a normalized broker frame."""
    key = f"{symbol}:{exchange}"
    raw = int(frame.get("volume") or 0)
    if frame.get("vtt") is not None:
        return _VOLUME_TRACKER.tick_volume(key, int(frame.get("vtt") or raw), cumulative=True)
    if frame.get("ltq") is not None:
        return _VOLUME_TRACKER.tick_volume(key, int(frame.get("ltq")), cumulative=False)
    return raw


def _decimal(value: Any, default: str = "0") -> Decimal:
    return Decimal(str(value if value is not None else default))


def _positive_or_none(value: Decimal) -> Decimal | None:
    return value if value > 0 else None


def normalize_broker_quote(
    raw_quote: Any,
    instrument_id: InstrumentId,
    *,
    broker_id: str,
    now: datetime | None = None,
) -> QuoteSnapshot:
    """Map broker-native quote payloads to ``QuoteSnapshot``."""
    event_time = now or get_current_clock().now()
    if isinstance(raw_quote, dict):
        ohlc = raw_quote.get("ohlc") or {}
        ltp = _decimal(raw_quote.get("last_price", raw_quote.get("ltp", 0)))
        bid = _decimal(
            raw_quote.get("bid", raw_quote.get("bid_price", raw_quote.get("best_bid", 0)))
        )
        ask = _decimal(
            raw_quote.get("ask", raw_quote.get("ask_price", raw_quote.get("best_ask", 0)))
        )
        high = _decimal(raw_quote.get("high", ohlc.get("high", 0)))
        low = _decimal(raw_quote.get("low", ohlc.get("low", 0)))
        open_ = _decimal(raw_quote.get("open", ohlc.get("open", 0)))
        close = _decimal(
            raw_quote.get("close", raw_quote.get("prev_close", ohlc.get("close", 0)))
        )
        volume = int(raw_quote.get("volume", 0) or 0)
        oi = int(raw_quote.get("oi", 0) or 0)
    else:
        ltp = _decimal(getattr(raw_quote, "ltp", 0) or 0)
        bid = _decimal(getattr(raw_quote, "bid", 0) or 0)
        ask = _decimal(getattr(raw_quote, "ask", 0) or 0)
        high = _decimal(getattr(raw_quote, "high", 0) or 0)
        low = _decimal(getattr(raw_quote, "low", 0) or 0)
        open_ = _decimal(getattr(raw_quote, "open", 0) or 0)
        close = _decimal(getattr(raw_quote, "close", 0) or 0)
        volume = int(getattr(raw_quote, "volume", 0) or 0)
        oi = int(getattr(raw_quote, "oi", 0) or 0)

    return QuoteSnapshot(
        instrument=InstrumentRef(
            symbol=instrument_id.underlying,
            exchange=instrument_id.exchange,
        ),
        ltp=ltp,
        event_time=event_time,
        provenance=DataProvenance(
            source=SourceIdentity(broker_id=broker_id),
            fetched_at=event_time,
            request_id="",
            confidence=ProvenanceConfidence.AUTHORITATIVE,
        ),
        bid=_positive_or_none(bid),
        ask=_positive_or_none(ask),
        high=_positive_or_none(high),
        low=_positive_or_none(low),
        open=_positive_or_none(open_),
        close=_positive_or_none(close),
        volume=volume,
        oi=oi,
    )
