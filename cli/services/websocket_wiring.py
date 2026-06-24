"""WebSocket Wiring — reserves market feed lifecycle slots.

Dhan order stream WebSocket services are owned by
:meth:`brokers.dhan.factory.BrokerFactory._wire_websocket_services`.
This module only reserves the market-feed lifecycle placeholder.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brokers.common.gateway import MarketDataGateway
    from infrastructure.lifecycle import LifecycleManager

logger = logging.getLogger(__name__)


def start_websocket_services(
    gateway: MarketDataGateway | None,
    lifecycle: LifecycleManager,
) -> None:
    """Reserve WebSocket lifecycle slots for on-demand market feeds.

    Order stream wiring is handled in the Dhan factory when ``event_bus``
    and ``lifecycle`` are provided. Market feeds are created when strategies
    subscribe via ``gateway.stream()``.
    """
    conn = getattr(gateway, "_conn", None) if gateway else None
    if conn is None:
        return

    if conn.order_stream is not None:
        logger.debug("order_stream_already_wired_by_factory")
    else:
        logger.debug("order_stream_not_wired; factory should register when event_bus is set")

    logger.debug("market_feed_placeholder_reserved")
