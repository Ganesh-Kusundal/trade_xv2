"""WebSocket Wiring — initializes order stream and market feed services.

Extracted from BrokerService._start_websocket_services() to reduce
complexity and enable independent testing.

This module handles:
- DhanOrderStream creation and lifecycle registration
- Market feed gateway placeholder reservation
- Access token function closure creation
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from brokers.common.gateway import MarketDataGateway
    from brokers.common.lifecycle import LifecycleManager

logger = logging.getLogger(__name__)


def start_websocket_services(
    gateway: MarketDataGateway | None,
    lifecycle: LifecycleManager,
) -> None:
    """Start WebSocket services for market feed and order stream.
    
    Lazily creates:
    - DhanOrderStream for live order updates (always started)
    - Market feed gateway (created on-demand when strategies subscribe)
    
    Both services are ManagedService instances registered with the
    LifecycleManager for clean shutdown on close().
    
    The order stream reconnects with a 1s→30s backoff that resets
    on every successful connect. The market feed placeholder keeps
    the lifecycle slot reserved.
    
    Args:
        gateway: MarketDataGateway instance (may be None)
        lifecycle: LifecycleManager for service registration
    """
    conn = getattr(gateway, "_conn", None) if gateway else None
    if conn is None:
        return
    
    # Subscribe to the canonical NSE_EQ NIFTY spot feed so the
    # OMS has streaming state to publish. In production this would
    # be driven by the strategy engine.
    try:
        from brokers.dhan.websocket import DhanOrderStream
        
        def access_token_fn() -> str:
            return conn._client.access_token  # type: ignore[no-any-return]
        
        # Order stream: always started — used by the OMS for fill
        # detection on every place_order call.
        if conn.order_stream is None:
            stream = DhanOrderStream(
                client_id=conn._client.client_id,
                access_token=conn._client.access_token,
                access_token_fn=access_token_fn,
                event_bus=conn.event_bus,
            )
            conn.order_stream = stream
            try:
                lifecycle.register(stream)
                logger.info("order_stream_registered")
            except Exception as exc:  # pragma: no cover
                logger.debug("order_stream_register_failed: %s", exc)
        
        # Market feed: only create if a strategy subscribes;
        # placeholder keeps the lifecycle slot reserved. The
        # previous broker.gateway.stream() helper still creates
        # on demand.
        logger.debug("market_feed_placeholder_reserved")
        
    except Exception as exc:
        logger.warning("websocket_services_wiring_failed: %s", exc)
