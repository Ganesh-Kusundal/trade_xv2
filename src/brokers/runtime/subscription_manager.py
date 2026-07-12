"""SubscriptionManager — coordinates live-data subscriptions for instruments.

Thin coordinator over ``Instrument.subscribe`` / ``DataProvider.subscribe``.
Owns the set of active handles so callers can manage them centrally.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

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
        handle = instrument.subscribe(callback, depth=depth)
        if handle is not None:
            self._handles[str(instrument.id)] = handle
        return handle

    def unsubscribe(self, instrument: Instrument) -> None:
        key = str(instrument.id)
        handle = self._handles.pop(key, None)
        if handle is not None:
            try:
                handle.unsubscribe()
            except Exception:
                pass
        else:
            instrument.unsubscribe()

    def active(self) -> list[str]:
        return list(self._handles.keys())

    def clear(self) -> None:
        for handle in self._handles.values():
            try:
                handle.unsubscribe()
            except Exception:
                pass
        self._handles.clear()