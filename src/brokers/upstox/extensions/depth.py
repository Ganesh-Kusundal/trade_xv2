"""Upstox 30-level depth extension — broker-specific capability as a domain plugin.

Wraps ``BrokerGateway.stream_depth(depth_type="DEPTH_30")`` behind the domain
``Extension`` ABC. Domain code discovers this via
``instrument.get_extension("depth_30")`` and calls ``full_depth()`` without
knowing anything about Upstox, WebSocket feeds, or the underlying transport.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain import MarketDepth
from domain.constants.exchanges import NSE
from domain.constants.segments import nse_eligible_segments
from domain.extensions.base import Extension
from domain.value_objects.capability import Capability

if TYPE_CHECKING:
    from domain.instruments.instrument_id import InstrumentId


class UpstoxDepth30Extension(Extension):
    """30-level market depth via Upstox WebSocket (L3 / full_d30).

    Capabilities
    ------------
    ``depth_30`` — 30-level bid/ask ladder for NSE segments.
    """

    _NSE_SEGMENTS = nse_eligible_segments()

    def __init__(self, gateway: Any) -> None:
        self._gw = gateway

    @property
    def name(self) -> str:
        return "depth_30"

    @property
    def broker(self) -> str:
        return "upstox"

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def capabilities(self) -> tuple[Capability, ...]:
        return (Capability.DEPTH_30,)

    def is_available_for(self, instrument_id: InstrumentId) -> bool:
        return instrument_id.exchange in self._NSE_SEGMENTS

    def full_depth(self, on_depth: Any | None = None) -> MarketDepth:
        """Fetch or subscribe to 30-level depth for this instrument.

        Parameters
        ----------
        on_depth:
            Optional callback ``(MarketDepth) -> None`` for live depth updates.
            When provided, the WebSocket feed is started and the callback fires
            on each depth packet.

        Returns the most-recently cached ``MarketDepth`` (up to 30 levels per
        side).
        """
        return self._gw.stream_depth(
            symbol=getattr(self, "_symbol", ""),
            exchange=getattr(self, "_exchange", NSE),
            depth_type="DEPTH_30",
            on_depth=on_depth,
        )

    def for_instrument(self, symbol: str, exchange: str = NSE) -> UpstoxDepth30Extension:
        """Bind the extension to a specific instrument for method calls."""
        ext = UpstoxDepth30Extension(self._gw)
        ext._symbol = symbol  # type: ignore[attr-defined]
        ext._exchange = exchange  # type: ignore[attr-defined]
        return ext

    def __repr__(self) -> str:
        return "UpstoxDepth30Extension(broker='upstox')"
