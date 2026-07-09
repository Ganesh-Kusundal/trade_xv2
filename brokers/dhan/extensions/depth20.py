"""Dhan 20-level depth extension — broker-specific capability as a domain plugin.

Wraps ``BrokerGateway.depth_20()`` behind the domain ``Extension`` ABC.
Domain code discovers this via ``instrument.get_extension("depth20")`` and
calls ``full_depth()`` without knowing anything about Dhan, WebSocket feeds,
or the underlying transport.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain import MarketDepth
from domain.extensions.base import Extension
from domain.value_objects.capability import Capability

if TYPE_CHECKING:
    from domain.instruments.instrument_id import InstrumentId


class DhanDepth20Extension(Extension):
    """20-level market depth via Dhan WebSocket.

    Capabilities
    ------------
    ``depth_20`` — 20-level bid/ask ladder for NSE segments.
    """

    _NSE_SEGMENTS = frozenset({"NSE", "NSE_EQ", "NFO", "NSE_FNO", "IDX_I"})

    def __init__(self, gateway: Any) -> None:
        self._gw = gateway

    @property
    def name(self) -> str:
        return "depth_20"

    @property
    def broker(self) -> str:
        return "dhan"

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def capabilities(self) -> tuple[Capability, ...]:
        return (Capability(name="depth_20", supported=True),)

    def is_available_for(self, instrument_id: InstrumentId) -> bool:
        return instrument_id.exchange in self._NSE_SEGMENTS

    def full_depth(self, on_depth: Any | None = None) -> MarketDepth:
        """Fetch or subscribe to 20-level depth for this instrument.

        Parameters
        ----------
        on_depth:
            Optional callback ``(MarketDepth) -> None`` for live depth updates.
            When provided, the WebSocket feed is started and the callback fires
            on each depth packet.

        Returns the most-recently cached ``MarketDepth`` (up to 20 levels per
        side). Falls back to 5-level REST if no WebSocket data yet.
        """
        return self._gw.depth_20(
            symbol=getattr(self, "_symbol", ""),
            exchange=getattr(self, "_exchange", "NSE"),
            on_depth=on_depth,
        )

    def for_instrument(self, symbol: str, exchange: str = "NSE") -> "DhanDepth20Extension":
        """Bind the extension to a specific instrument for method calls."""
        ext = DhanDepth20Extension(self._gw)
        ext._symbol = symbol  # type: ignore[attr-defined]
        ext._exchange = exchange  # type: ignore[attr-defined]
        return ext

    def __repr__(self) -> str:
        return "DhanDepth20Extension(broker='dhan')"
