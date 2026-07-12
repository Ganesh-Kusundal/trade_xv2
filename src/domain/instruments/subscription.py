"""Subscription — first-class domain object for a live market-data stream.

Previously ``Instrument.subscribe()`` returned the raw provider ``Subscription``
protocol handle. Now it returns this tracked object, which owns the subscription
lifecycle and emits ``TICK`` / ``DEPTH_UPDATED`` domain events as data arrives,
so consumers collaborate through events rather than tight coupling.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from domain.events.types import DomainEvent, EventType

if TYPE_CHECKING:
    from collections.abc import Callable
    from domain.events.bus import DomainEventBus
    from domain.instruments.instrument_id import InstrumentId
    from domain.ports.protocols import Subscription as ProviderSubscription


class Subscription:
    """Tracked live-data subscription owned by an :class:`Instrument`.

    Wraps the provider's subscription handle, counts ticks/depths, and publishes
    domain events through the injected ``event_bus``.
    """

    def __init__(
        self,
        instrument_id: "InstrumentId",
        *,
        event_bus: "DomainEventBus | None" = None,
        depth: bool = False,
    ) -> None:
        self._instrument_id = instrument_id
        self._event_bus = event_bus
        self._depth = depth
        self._provider_subscription: "ProviderSubscription | None" = None
        self._teardown: "Callable[[], None] | None" = None
        self._started_at = datetime.now(timezone.utc)
        self._ended_at: datetime | None = None
        self._tick_count = 0
        self._depth_count = 0
        self._active = False

    # ── Wiring (called by Instrument.subscribe) ──────────────────────

    def _attach(
        self,
        provider_subscription: "ProviderSubscription",
        teardown: "Callable[[], None]",
    ) -> None:
        """Bind the underlying provider handle and aggregate teardown."""
        self._provider_subscription = provider_subscription
        self._teardown = teardown
        self._active = True

    # ── Event ingestion (called on each provider tick) ───────────────

    def _on_tick(self, instrument_id: "InstrumentId", payload: Any) -> None:
        """Record a tick/depth and publish the corresponding domain event."""
        from domain.entities.market import MarketDepth

        if isinstance(payload, MarketDepth):
            self._depth_count += 1
            event_type = EventType.DEPTH_UPDATED
        else:
            self._tick_count += 1
            event_type = EventType.TICK
        if self._event_bus is not None:
            event_payload: dict[str, Any] = {
                "symbol": instrument_id.underlying,
                "exchange": instrument_id.exchange,
                "asset_type": instrument_id.asset_type,
            }
            ltp = getattr(payload, "ltp", None) or getattr(payload, "last_price", None)
            if ltp is not None:
                event_payload["ltp"] = float(ltp)
            if isinstance(payload, dict):
                if "ltp" in payload:
                    event_payload["ltp"] = float(payload["ltp"])
                if "last_price" in payload:
                    event_payload["ltp"] = float(payload["last_price"])
            self._event_bus.publish(DomainEvent.now(event_type, event_payload))

    # ── Lifecycle ─────────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        if self._provider_subscription is not None:
            try:
                return self._provider_subscription.is_active and self._active
            except Exception:
                return self._active
        return self._active

    @property
    def tick_count(self) -> int:
        return self._tick_count

    @property
    def depth_count(self) -> int:
        return self._depth_count

    @property
    def started_at(self) -> datetime:
        return self._started_at

    @property
    def ended_at(self) -> datetime | None:
        return self._ended_at

    def unsubscribe(self) -> None:
        """Tear down the stream and publish SUBSCRIPTION_ENDED."""
        if self._provider_subscription is not None:
            try:
                self._provider_subscription.unsubscribe()
            except Exception:
                pass
        if self._teardown is not None:
            try:
                self._teardown()
            except Exception:
                pass
        self._active = False
        self._ended_at = datetime.now(timezone.utc)
        if self._event_bus is not None:
            self._event_bus.publish(
                DomainEvent.now(
                    EventType.SUBSCRIPTION_ENDED,
                    {
                        "symbol": self._instrument_id.underlying,
                        "exchange": self._instrument_id.exchange,
                    },
                )
            )

    def __repr__(self) -> str:
        return (
            f"Subscription({self._instrument_id}, "
            f"active={self.is_active}, ticks={self._tick_count}, depths={self._depth_count})"
        )
