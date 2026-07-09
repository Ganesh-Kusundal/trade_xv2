"""PollingMarketFeed — REST polling fallback for market data.

Extracted from the former monolithic ``brokers/dhan/websocket.py`` (Task 5.1).
Used when the WebSocket feed is unavailable; polls the Dhan batch LTP API
at regular intervals and dispatches quote callbacks.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal

from brokers.dhan.reconnecting_service import ReconnectingServiceMixin
from brokers.dhan.segments import EXCHANGE_TO_SEGMENT
from brokers.dhan.websocket._helpers import _to_decimal
from domain import Quote
from domain.events import DomainEvent
from domain.lifecycle_health import HealthStatus
from infrastructure.event_bus.event_bus import EventBus
from infrastructure.lifecycle.lifecycle import HealthState, ManagedService

logger = logging.getLogger(__name__)


class PollingMarketFeed(ReconnectingServiceMixin, ManagedService):
    """REST polling fallback for market data when WebSocket is unavailable.

    Polls /marketfeed/ltp at regular intervals and dispatches quote callbacks.
    Same callback interface as DhanMarketFeed for drop-in replacement.

    Implements :class:`ManagedService` (Phase B / B5) so the broker's
    :class:`LifecycleManager` can start, stop, and health-check the
    background polling thread. This class's ``stop`` was the only
    one of the three that already joined — that behaviour is preserved
    and surfaced through the new ``name``/``start``/``stop``/``health``
    contract.
    """

    name = "dhan.polling_market_feed"

    def __init__(
        self,
        http_client,
        resolver,
        instruments: list[tuple],
        interval_seconds: float = 2.0,
        event_bus: EventBus | None = None,
    ):
        """
        Args:
            http_client: DhanHttpClient instance
            resolver: SymbolResolver for security_id → symbol lookup
            instruments: List of (exchange_str, security_id_str, mode_str) tuples
            interval_seconds: Polling interval (default 2s)
            event_bus: Optional EventBus to publish TICK events to so polled
                quotes are persisted even when the live WebSocket is down.
        """
        self._client = http_client
        self._resolver = resolver
        self._instruments = instruments
        self._interval = interval_seconds
        self._event_bus = event_bus
        self._quote_callbacks: list[Callable[[dict], None]] = []
        self._thread: threading.Thread | None = None
        # Plan §7.2: shared reconnect / message-tracking state.
        self._init_reconnect_state()

    def connect(self) -> None:
        """Deprecated alias for :meth:`start`."""
        self.start()

    def start(self) -> None:
        """ManagedService protocol: start the polling thread.

        Idempotent — re-calling while the thread is alive is a no-op.
        """
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._is_connected = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            name=self.name,
            daemon=True,
        )
        self._thread.start()
        logger.info("Polling market feed started (interval=%ss)", self._interval)

    def disconnect(self, timeout_seconds: float = 5.0) -> None:
        """Deprecated alias for :meth:`stop`."""
        self.stop(timeout_seconds=timeout_seconds)

    def stop(self, timeout_seconds: float = 5.0) -> None:
        """ManagedService protocol: stop the polling thread.

        Sets ``_stop_event`` and joins the thread within
        ``timeout_seconds``. The previous ``disconnect()`` already
        joined at a 5s timeout — this behaviour is preserved
        and exposed through the ManagedService contract.
        Idempotent.
        """
        self._stop_event.set()
        self._is_connected = False
        if self._thread:
            self._thread.join(timeout=timeout_seconds)
            if self._thread.is_alive():
                logger.warning(
                    "dhan.polling_market_feed thread did not stop within %ss",
                    timeout_seconds,
                )
        logger.info("Polling market feed stopped")

    def health(self) -> HealthStatus:
        """ManagedService protocol: return a point-in-time health snapshot."""
        thread_alive = bool(self._thread and self._thread.is_alive())
        is_connected = self._is_connected
        if thread_alive and is_connected:
            state = HealthState.HEALTHY
            detail = "polling"
        elif thread_alive and not is_connected:
            state = HealthState.DEGRADED
            detail = "thread running but not connected"
        else:
            state = HealthState.STOPPED
            detail = "not started"
        return HealthStatus(
            state=state,
            service=self.name,
            last_check=datetime.now(timezone.utc),
            detail=detail,
            metrics={"connected": is_connected, "thread_alive": thread_alive},
        )

    def on_quote(self, callback: Callable[[dict], None]) -> None:
        """Register callback for quote updates."""
        self._register_callback(self._quote_callbacks, callback)

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    # Dhan batch LTP API supports up to 1000 symbols per request.
    _BATCH_SIZE = 1000

    def _poll_loop(self) -> None:
        """Poll instruments using batch LTP API and dispatch callbacks.

        Task 2.6: replaced per-instrument POST loop with a single batch
        POST per segment (up to 1000 symbols per request). This reduces
        HTTP overhead from N requests per cycle to ceil(N/1000).
        """
        while not self._stop_event.is_set():
            try:
                self._poll_batch()
            except Exception as exc:
                logger.warning("Polling batch error: %s", exc)
            self._stop_event.wait(timeout=self._interval)

    def _poll_batch(self) -> None:
        """Execute a single batch poll cycle across all instruments."""
        from collections import defaultdict

        # Group instruments by segment for batch requests
        segment_groups: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for exchange, security_id, _mode in self._instruments:
            if self._stop_event.is_set():
                return
            segment = EXCHANGE_TO_SEGMENT.get(str(exchange).upper(), "NSE_EQ")
            sid = int(security_id)
            segment_groups[segment].append((str(security_id), sid))

        for segment, sid_list in segment_groups.items():
            if self._stop_event.is_set():
                return
            # Chunk into batches of _BATCH_SIZE (Dhan API limit)
            for chunk_start in range(0, len(sid_list), self._BATCH_SIZE):
                chunk = sid_list[chunk_start : chunk_start + self._BATCH_SIZE]
                sids = [sid for _, sid in chunk]
                sid_lookup = {sid: sec_id for sec_id, sid in chunk}
                try:
                    data = self._client.post(
                        "/marketfeed/ltp", json={segment: sids}
                    )
                    segment_data = data.get("data", {}).get(segment, {})
                    self._dispatch_batch_results(segment_data, sid_lookup)
                    # Plan §7.2: shared message-tracking through the mixin.
                    self._note_message_received()
                except Exception as exc:
                    logger.warning(
                        "Polling batch error for segment %s: %s", segment, exc
                    )

    def _dispatch_batch_results(
        self, segment_data: dict, sid_lookup: dict[int, str]
    ) -> None:
        """Parse batch response and dispatch quotes to callbacks."""
        callbacks = self._snapshot_callbacks(self._quote_callbacks)
        for sid, raw in segment_data.items():
            sec_id = sid_lookup.get(int(sid))
            if sec_id is None:
                continue
            ltp = raw.get("last_price", 0)
            symbol = sec_id
            if self._resolver:
                try:
                    inst = self._resolver.get_by_security_id(sec_id)
                    if inst:
                        symbol = inst.symbol
                except Exception as exc:
                    logger.warning("Polling resolver error for %s: %s", sec_id, exc)
            # Populate OHLC/volume from the polled quote fields when present;
            # only fall back to zero when the field is genuinely absent.
            quote = {
                "symbol": symbol,
                "security_id": sec_id,
                "ltp": Decimal(str(ltp)),
                "open": Decimal(str(raw["open"])) if raw.get("open") else Decimal("0"),
                "high": Decimal(str(raw["high"])) if raw.get("high") else Decimal("0"),
                "low": Decimal(str(raw["low"])) if raw.get("low") else Decimal("0"),
                "close": Decimal(str(raw["close"])) if raw.get("close") else Decimal("0"),
                "volume": int(raw.get("volume", 0) or 0),
                "change": Decimal(str(raw["change"])) if raw.get("change") else Decimal("0"),
            }
            for cb in callbacks:
                try:
                    cb(quote)
                except Exception as exc:
                    logger.error("Polling callback error: %s", exc)
            # Publish TICK so polled quotes are persisted during a WS outage.
            self._publish_tick(quote)

    def _publish_tick(self, quote: dict, correlation_id: str | None = None) -> None:
        """Publish a TICK event to the event bus (mirrors DhanMarketFeed §7.7).

        A zero/missing LTP is dropped (it is a dangerous false signal for
        downstream strategies) so it is never persisted as a real tick.
        OHLC/volume may be zero for freshly-listed symbols — that is allowed.
        """
        if self._event_bus is None:
            return
        try:
            ltp_raw = quote.get("ltp")
            symbol = quote.get("symbol", "")
            ltp = _to_decimal(ltp_raw)
            if ltp_raw is None or ltp == 0:
                logger.warning(
                    "tick_dropped_missing_or_zero_ltp: symbol=%s", symbol or "<unknown>"
                )
                return
            if not symbol:
                logger.warning("tick_dropped_missing_symbol")
                return
            q = Quote(
                symbol=symbol,
                ltp=ltp,
                open=_to_decimal(quote.get("open")),
                high=_to_decimal(quote.get("high")),
                low=_to_decimal(quote.get("low")),
                close=_to_decimal(quote.get("close")),
                volume=quote.get("volume", 0),
                change=_to_decimal(quote.get("change")),
            )
            self._event_bus.publish(
                DomainEvent.now(
                    "TICK",
                    {"quote": q},
                    symbol=q.symbol,
                    source="PollingMarketFeed",
                    correlation_id=correlation_id,
                )
            )
        except Exception as exc:
            logger.error("EventBus TICK publish error: %s", exc)
