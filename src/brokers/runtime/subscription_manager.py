"""SubscriptionManager — coordinates live-data subscriptions for instruments.

Routes through ``Instrument``'s subscription core so instrument state/callbacks
stay consistent with ``session.gateway.subscribe``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from domain.instruments.instrument import Instrument
    from domain.ports.protocols import SubscriptionHandle


class SubscriptionManager:
    """Tracks and coordinates instrument subscriptions."""

    def __init__(self) -> None:
        self._handles: dict[str, SubscriptionHandle] = {}

    def subscribe(
        self,
        instrument: Instrument,
        callback: Callable | None = None,
        *,
        depth: bool = False,
    ) -> SubscriptionHandle | None:
        # Prefer instrument core (updates Instrument state); fall back to provider.
        core = getattr(instrument, "_subscribe_core", None)
        if callable(core):
            handle = core(callback, depth=depth)
        else:
            provider = instrument._resolve_provider()
            handle = provider.subscribe(instrument.id, callback, depth=depth)
        if handle is not None:
            self._handles[str(instrument.id)] = handle
        return handle

    def unsubscribe(self, instrument: Instrument) -> None:
        key = str(instrument.id)
        self._handles.pop(key, None)
        unsub = getattr(instrument, "unsubscribe", None)
        if callable(unsub):
            unsub()

    def active(self) -> list[str]:
        return list(self._handles.keys())

    def clear(self) -> None:
        for handle in list(self._handles.values()):
            try:
                handle.unsubscribe()
            except Exception:
                pass
        self._handles.clear()
