"""Upstox-specific broker extensions for v2 gateway.

Concrete extensions registered on ``UpstoxGateway.extensions``:
- ``UpstoxDepth20Extension`` — 20-level depth via WebSocket
- ``UpstoxDepth200Extension`` — 200-level depth via WebSocket

These are plain objects looked up via ``gateway.extension(UpstoxDepth20Extension)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from domain.entities import MarketDepth
from domain.value_objects import InstrumentId

if TYPE_CHECKING:
    from plugins.brokers.upstox.adapters.streaming import UpstoxStreamingAdapter


@dataclass
class UpstoxDepth20Extension:
    """20-level market depth via Upstox WebSocket feed.

    Registered on the UpstoxGateway extensions registry so callers can do::

        ext = gateway.extension(UpstoxDepth20Extension)
        ext.full_depth(instrument_id, on_depth=callback)

    Delegates the live subscription to the gateway's streaming adapter, which
    reuses Upstox's quote feed (it already carries ``depth.{buy,sell}``).
    """

    _streaming: "UpstoxStreamingAdapter | None" = field(default=None, repr=False)

    @property
    def name(self) -> str:
        return "depth_20"

    @property
    def broker(self) -> str:
        return "upstox"

    def full_depth(
        self,
        instrument_id: InstrumentId,
        on_depth: Callable[[MarketDepth], None] | None = None,
    ) -> MarketDepth | None:
        """Subscribe to 20-level depth for *instrument_id*.

        Returns the most recently cached depth (or ``None`` until the first
        packet arrives). The *on_depth* callback fires on each depth packet.
        """
        if self._streaming is None:
            return None
        return self._streaming.stream_depth(instrument_id, on_depth=on_depth)

    def __repr__(self) -> str:
        return "UpstoxDepth20Extension(broker='upstox')"


@dataclass
class UpstoxDepth200Extension:
    """200-level market depth via Upstox WebSocket feed.

    Same shape as :class:`UpstoxDepth20Extension` but for 200 levels.
    """

    _streaming: "UpstoxStreamingAdapter | None" = field(default=None, repr=False)

    @property
    def name(self) -> str:
        return "depth_200"

    @property
    def broker(self) -> str:
        return "upstox"

    def full_depth(
        self,
        instrument_id: InstrumentId,
        on_depth: Callable[[MarketDepth], None] | None = None,
    ) -> MarketDepth | None:
        """Subscribe to 200-level depth for *instrument_id*."""
        if self._streaming is None:
            return None
        return self._streaming.stream_depth(instrument_id, on_depth=on_depth)

    def __repr__(self) -> str:
        return "UpstoxDepth200Extension(broker='upstox')"
