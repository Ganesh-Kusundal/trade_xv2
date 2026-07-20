"""InstrumentStreamingMixin — subscription / callback registration.

Extracted from the Instrument god class (KD-202).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from domain.entities.market import MarketDepth, QuoteSnapshot
from domain.value_objects.state import SubscriptionState, SubscriptionStatus

if TYPE_CHECKING:
    import threading

    from domain.instruments.instrument_id import InstrumentId
    from domain.ports.protocols import DataProvider, SubscriptionHandle
    from domain.value_objects.state import InstrumentState

logger = logging.getLogger(__name__)


class InstrumentStreamingMixin:
    """Mixin providing live data subscription / callback methods for Instrument.

    Expects these attributes on ``self`` (provided by ``Instrument.__init__``):

        _provider, _lock, _state, _callbacks, _subscription, _id,
        symbol, exchange, _resolve_provider()
    """

    # ── Attribute declarations (provided by concrete class) ────────────

    _lock: threading.RLock
    _state: InstrumentState
    _callbacks: dict[str, list[Callable]]
    _subscription: SubscriptionHandle | None
    _id: InstrumentId
    symbol: str
    exchange: str

    def _resolve_provider(self) -> DataProvider:  # pragma: no cover
        ...

    # ── Subscription ──────────────────────────────────────────────────

    def subscribe(
        self,
        callback: Callable[[InstrumentId, Any], None] | None = None,
        *,
        depth: bool = False,
    ) -> SubscriptionHandle | None:
        """Subscribe to live data."""
        provider = self._resolve_provider()

        def _wrapped(iid: InstrumentId, payload: Any) -> None:
            # Update state atomically
            with self._lock:
                if isinstance(payload, MarketDepth):
                    self._state = self._state.with_depth(payload)
                elif isinstance(payload, QuoteSnapshot):
                    self._state = self._state.with_quote(payload)
                sub = self._state.subscription
                if not sub.is_active:
                    self._state = self._state.with_subscription(
                        SubscriptionState(
                            status=SubscriptionStatus.SUBSCRIBED,
                            symbol=self.symbol,
                            exchange=self.exchange,
                            started_at=sub.started_at or datetime.now(timezone.utc),
                        )
                    )
            # Invoke registered callbacks (outside lock to avoid deadlock)
            with self._lock:
                tick_callbacks = list(self._callbacks.get("tick", []))
            for cb in tick_callbacks:
                try:
                    cb(payload)
                except Exception:
                    logger.exception("tick callback %r failed for %s", cb, self._id)
            # Invoke user callback
            if callback is not None:
                callback(iid, payload)

        handle = provider.subscribe(self._id, _wrapped, depth=depth)
        self._subscription = handle
        with self._lock:
            self._state = self._state.with_subscription(
                SubscriptionState(
                    status=SubscriptionStatus.SUBSCRIBED,
                    symbol=self.symbol,
                    exchange=self.exchange,
                    started_at=datetime.now(timezone.utc),
                )
            )
        return handle

    def unsubscribe(self) -> None:
        """Tear down live subscription."""
        if self._subscription is not None:
            self._subscription.unsubscribe()
            self._subscription = None
        with self._lock:
            self._state = self._state.with_unsubscribed()

    # ── Callback Registration ─────────────────────────────────────────

    def on_tick(self, callback: Callable) -> None:
        """Register tick callback."""
        with self._lock:
            self._callbacks["tick"] = self._callbacks["tick"] + [callback]

    def on_quote(self, callback: Callable) -> None:
        """Register quote callback."""
        with self._lock:
            self._callbacks["quote"] = self._callbacks["quote"] + [callback]

    def on_depth(self, callback: Callable) -> None:
        """Register depth callback."""
        with self._lock:
            self._callbacks["depth"] = self._callbacks["depth"] + [callback]

    def on_disconnect(self, callback: Callable) -> None:
        """Register disconnect callback."""
        with self._lock:
            self._callbacks["disconnect"] = self._callbacks["disconnect"] + [callback]

    def on_reconnect(self, callback: Callable) -> None:
        """Register reconnect callback."""
        with self._lock:
            self._callbacks["reconnect"] = self._callbacks["reconnect"] + [callback]
