"""Event-bus publishing pipeline for Dhan market feed ticks and depth.

Extracted from :class:`DhanMarketFeed` so the feed façade stays focused on
orchestration (connection + subscription + message routing).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Callable

from domain import DepthLevel, MarketDepth, Quote
from domain.events import DomainEvent

logger = logging.getLogger(__name__)


class MarketFeedPublisher:
    """Strict-mode TICK/DEPTH publisher with drop counters."""

    def __init__(
        self,
        event_bus: Any | None,
        next_sequence: Callable[[str], int],
        *,
        to_decimal: Callable[[Any], Decimal],
    ) -> None:
        self._event_bus = event_bus
        self._next_sequence = next_sequence
        self._to_decimal = to_decimal
        self.published_ticks = 0
        self.dropped_ticks = 0
        self.published_depths = 0
        self.dropped_depths = 0

    def publish_tick(self, quote: dict, correlation_id: str | None = None) -> None:
        if self._event_bus is None:
            return
        try:
            ltp_raw = quote.get("ltp")
            symbol = quote.get("symbol", "")
            ltp = self._to_decimal(ltp_raw)
            if ltp_raw is None or ltp == 0:
                self.dropped_ticks += 1
                self._inc_metric("dhan_ws_dropped_ticks_total")
                logger.warning("tick_dropped_missing_or_zero_ltp: symbol=%s", symbol or "<unknown>")
                return
            if not symbol:
                self.dropped_ticks += 1
                self._inc_metric("dhan_ws_dropped_ticks_total")
                logger.warning("tick_dropped_missing_symbol")
                return

            seq = self._next_sequence(symbol)
            quote["sequence"] = seq
            q = Quote(
                symbol=symbol,
                ltp=ltp,
                open=self._to_decimal(quote.get("open")),
                high=self._to_decimal(quote.get("high")),
                low=self._to_decimal(quote.get("low")),
                close=self._to_decimal(quote.get("close")),
                volume=quote.get("volume", 0),
                change=self._to_decimal(quote.get("change")),
                timestamp=quote.get("timestamp"),
            )
            self._event_bus.publish(
                DomainEvent.now(
                    "TICK",
                    {"quote": q},
                    symbol=q.symbol,
                    source="DhanMarketFeed",
                    correlation_id=correlation_id,
                )
            )
            self.published_ticks += 1
            self._inc_metric("dhan_ws_ticks_total")
        except Exception as exc:
            self.dropped_ticks += 1
            logger.error("EventBus TICK publish error: %s", exc)

    def publish_depth(self, depth: dict, correlation_id: str | None = None) -> None:
        if self._event_bus is None:
            return
        symbol = depth.get("symbol", "")
        if not symbol:
            self.dropped_depths += 1
            logger.warning("depth_dropped_missing_symbol")
            return
        try:
            d = depth.get("depth", {}) or {}
            bids = [
                DepthLevel(
                    price=Decimal(str(b.get("price", 0))),
                    quantity=int(b.get("quantity", 0)),
                    orders=int(b.get("orders", 0)),
                )
                for b in d.get("bids", [])
            ]
            asks = [
                DepthLevel(
                    price=Decimal(str(a.get("price", 0))),
                    quantity=int(a.get("quantity", 0)),
                    orders=int(a.get("orders", 0)),
                )
                for a in d.get("asks", [])
            ]
            if not bids and not asks:
                self.dropped_depths += 1
                logger.warning("depth_dropped_both_sides_empty: symbol=%s", symbol)
                return
            if bids and bids[0].price <= 0:
                self.dropped_depths += 1
                logger.warning(
                    "depth_dropped_invalid_bid_top: symbol=%s bid0=%s",
                    symbol,
                    bids[0].price,
                )
                return
            if asks and asks[0].price <= 0:
                self.dropped_depths += 1
                logger.warning(
                    "depth_dropped_invalid_ask_top: symbol=%s ask0=%s",
                    symbol,
                    asks[0].price,
                )
                return
            md = MarketDepth(bids=bids, asks=asks)
            self._event_bus.publish(
                DomainEvent.now(
                    "DEPTH",
                    {"depth": md},
                    symbol=symbol,
                    source="DhanMarketFeed",
                    correlation_id=correlation_id,
                )
            )
            self.published_depths += 1
        except Exception as exc:
            self.dropped_depths += 1
            logger.error("EventBus DEPTH publish error: %s", exc)

    @staticmethod
    def _inc_metric(name: str) -> None:
        try:
            from brokers.dhan.resilience import metrics as m

            getattr(m, name).inc()
        except Exception:
            pass
