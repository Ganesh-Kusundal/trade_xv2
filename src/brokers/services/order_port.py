"""Gateway OrderPlacementPort accessor for broker services (SS-02)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.ports.order_placement import OrderPlacementPort

if TYPE_CHECKING:
    from brokers.session import BrokerSession

from .capabilities import _session_gateway


def order_port_from_session(session: BrokerSession) -> OrderPlacementPort | None:
    """Return gateway when it implements :class:`OrderPlacementPort`."""
    gw = _session_gateway(session)
    if gw is None or not hasattr(gw, "place_order"):
        return None
    return gw  # type: ignore[return-value]


__all__ = ["order_port_from_session"]
