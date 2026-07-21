"""InstrumentStreamingMixin — subscription core + callback registration.

Public streaming entry: ``session.gateway.subscribe([instrument])``.
``Instrument.subscribe`` was removed; ``_subscribe_core`` remains for the
gateway ``SubscriptionManager`` and typed helpers.
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
    """Mixin providing live data subscription core + callback methods.

    Expects these attributes on ``self`` (provided by ``Instrument.__init__``):

        _provider, _lock, _state, _callbacks, _subscription, _id,
        symbol, exchange, _resolve_provider()
    """

    _lock: threading.RLock
    _state: InstrumentState
    _callbacks: dict[str, list[Callable]]
    _subscription: SubscriptionHandle | None
    _id: InstrumentId
    symbol: str
    exchange: str

    def _resolve_provider(self) -> DataProvider:  # pragma: no cover
        ...

    def _subscribe_core(
        self,
        callback: Callable[[InstrumentId, Any], None] | None = None,
        *,
        depth: bool = False,
    ) -> SubscriptionHandle | None:
        """Activate live subscription and update instrument state."""
        provider = self._resolve_provider()

        def _wrapped(iid: InstrumentId, payload: Any) -> None:
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
            with self._lock:
                tick_callbacks = list(self._callbacks.get("tick", []))
            for cb in tick_callbacks:
                try:
                    cb(payload)
                except Exception:
                    logger.exception("tick callback %r failed for %s", cb, self._id)
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

    def on_tick(self, callback: Callable) -> None:
        with self._lock:
            self._callbacks["tick"] = self._callbacks["tick"] + [callback]

    def on_quote(self, callback: Callable) -> None:
        with self._lock:
            self._callbacks["quote"] = self._callbacks["quote"] + [callback]

    def on_depth(self, callback: Callable) -> None:
        with self._lock:
            self._callbacks["depth"] = self._callbacks["depth"] + [callback]

    def on_disconnect(self, callback: Callable) -> None:
        with self._lock:
            self._callbacks["disconnect"] = self._callbacks["disconnect"] + [callback]

    def on_reconnect(self, callback: Callable) -> None:
        with self._lock:
            self._callbacks["reconnect"] = self._callbacks["reconnect"] + [callback]
