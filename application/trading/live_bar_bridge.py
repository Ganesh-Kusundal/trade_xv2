"""Live TICK → bar-close → feature pipeline bridge (parity with replay).

ponytail: 1-minute bar aggregation only; upgrade path is shared BarAggregator
with configurable timeframe and session calendar.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from domain.events.types import DomainEvent, EventType

logger = logging.getLogger(__name__)


class LiveBarBridge:
    """Subscribe to TICK, emit BAR_CLOSED, run FeaturePipeline on each closed bar."""

    def __init__(
        self,
        event_bus: Any,
        *,
        pipeline: Any | None = None,
        strategy_pipeline: Any | None = None,
        bar_seconds: int = 60,
    ) -> None:
        self._bus = event_bus
        self._pipeline = pipeline
        self._strategy = strategy_pipeline
        self._bar_seconds = max(1, bar_seconds)
        self._open: dict[str, dict[str, Any]] = {}
        self._token = event_bus.subscribe(EventType.TICK.value, self._on_tick)

    def _on_tick(self, event: DomainEvent) -> None:
        payload = dict(event.payload)
        symbol = payload.get("symbol")
        ltp = payload.get("ltp")
        if not symbol or ltp is None:
            return
        ts = event.timestamp if event.timestamp.tzinfo else event.timestamp.replace(tzinfo=timezone.utc)
        bucket = int(ts.timestamp()) // self._bar_seconds
        key = f"{symbol}:{bucket}"
        bar = self._open.get(key)
        price = float(ltp)
        if bar is None:
            self._open[key] = {
                "symbol": symbol,
                "timestamp": ts,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": float(payload.get("volume", 0) or 0),
            }
            return
        bar["high"] = max(bar["high"], price)
        bar["low"] = min(bar["low"], price)
        bar["close"] = price
        bar["volume"] += float(payload.get("volume", 0) or 0)

        # Close prior bucket when a new bucket starts for the same symbol.
        for other_key, other_bar in list(self._open.items()):
            if other_key == key or not other_key.startswith(f"{symbol}:"):
                continue
            other_bucket = int(other_key.split(":")[-1])
            if other_bucket < bucket:
                self._emit_bar_closed(other_bar)
                del self._open[other_key]

    def _emit_bar_closed(self, bar: dict[str, Any]) -> None:
        self._bus.publish(
            DomainEvent.now(
                EventType.BAR_CLOSED.value,
                bar,
                symbol=bar["symbol"],
                source="LiveBarBridge",
            )
        )
        if self._pipeline is None:
            return
        try:
            import pandas as pd

            df = pd.DataFrame([bar])
            features = self._pipeline.transform(df)
            if self._strategy is not None and not features.empty:
                signal = self._strategy.evaluate_single(features.iloc[-1])
                if signal is not None:
                    self._bus.publish(
                        DomainEvent.now(
                            EventType.SIGNAL_GENERATED.value,
                            {"signal": signal, "symbol": bar["symbol"]},
                            symbol=bar["symbol"],
                            source="LiveBarBridge",
                        )
                    )
        except Exception as exc:
            logger.warning("LiveBarBridge pipeline failed for %s: %s", bar.get("symbol"), exc)

    def close(self) -> None:
        for bar in list(self._open.values()):
            self._emit_bar_closed(bar)
        self._open.clear()
        if hasattr(self._bus, "unsubscribe"):
            self._bus.unsubscribe(self._token)
