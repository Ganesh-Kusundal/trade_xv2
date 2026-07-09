"""StreamingService — orchestration wrapper for live market-data streaming.

Wraps a :class:`~domain.ports.protocols.DataProvider` so the ``Instrument``
never talks to a broker directly for subscriptions.  Pure domain layer:
no broker or transport imports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from domain.instruments.instrument_id import InstrumentId
    from domain.ports.protocols import DataProvider, SubscriptionHandle


class StreamingService:
    """Thin streaming accessor over a :class:`DataProvider` port."""

    def __init__(self, provider: DataProvider | None = None) -> None:
        self._provider = provider

    @property
    def provider(self) -> DataProvider | None:
        return self._provider

    def subscribe(
        self,
        instrument_id: Any,
        callback: Callable[..., Any],
        *,
        depth: bool = False,
    ) -> Any:
        if self._provider is None:
            return None
        return self._provider.subscribe(instrument_id, callback, depth=depth)

    def unsubscribe(self, handle: Any) -> None:
        if self._provider is None or handle is None:
            return None
        return self._provider.unsubscribe(handle)
