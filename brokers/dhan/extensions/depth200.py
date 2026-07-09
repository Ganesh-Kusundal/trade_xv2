"""Dhan 200-level depth extension — premium broker-specific capability.

Wraps ``BrokerGateway.depth_200()`` behind the domain ``Extension`` ABC.
Dhan allows only ONE instrument per depth-200 connection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain import MarketDepth
from domain.extensions.base import Extension
from domain.value_objects.capability import Capability

if TYPE_CHECKING:
    from domain.instruments.instrument_id import InstrumentId


class DhanDepth200Extension(Extension):
    """200-level market depth via Dhan WebSocket (premium tier).

    Capabilities
    ------------
    ``depth_200`` — 200-level bid/ask ladder for NSE segments.
    """

    _NSE_SEGMENTS = frozenset({"NSE", "NSE_EQ", "NFO", "NSE_FNO", "IDX_I"})

    def __init__(self, gateway: Any) -> None:
        self._gw = gateway

    @property
    def name(self) -> str:
        return "depth_200"

    @property
    def broker(self) -> str:
        return "dhan"

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def capabilities(self) -> tuple[Capability, ...]:
        return (Capability(name="depth_200", supported=True),)

    def is_available_for(self, instrument_id: InstrumentId) -> bool:
        return instrument_id.exchange in self._NSE_SEGMENTS

    def full_depth(self, on_depth: Any | None = None) -> MarketDepth:
        """Fetch or subscribe to 200-level depth for this instrument.

        Returns the most-recently cached ``MarketDepth`` (up to 200 levels).
        """
        return self._gw.depth_200(
            symbol=getattr(self, "_symbol", ""),
            exchange=getattr(self, "_exchange", "NSE"),
            on_depth=on_depth,
        )

    def for_instrument(self, symbol: str, exchange: str = "NSE") -> "DhanDepth200Extension":
        """Bind the extension to a specific instrument for method calls."""
        ext = DhanDepth200Extension(self._gw)
        ext._symbol = symbol  # type: ignore[attr-defined]
        ext._exchange = exchange  # type: ignore[attr-defined]
        return ext

    def __repr__(self) -> str:
        return "DhanDepth200Extension(broker='dhan')"
