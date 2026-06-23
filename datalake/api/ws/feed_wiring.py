"""Wire WebSocket market subscriptions to the active broker feed."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def subscribe_symbols_to_broker(symbols: list[str], exchange: str = "NSE") -> None:
    """Subscribe *symbols* on the live broker gateway so ticks reach the EventBus.

    Called when API WebSocket clients subscribe to market data. Uses the
    broker gateway's ``stream()`` method which deduplicates subscriptions.
    """
    if not symbols:
        return

    try:
        from datalake.api.deps import get_container

        container = get_container()
    except Exception:
        logger.debug("feed_wiring: service container unavailable")
        return

    broker_service = container.broker_service
    if broker_service is None:
        logger.warning("feed_wiring: no broker_service — cannot subscribe %s", symbols)
        return

    gateway = _resolve_gateway(broker_service)
    if gateway is None:
        logger.warning("feed_wiring: no gateway — cannot subscribe %s", symbols)
        return

    stream_fn = getattr(gateway, "stream", None)
    if stream_fn is None:
        logger.warning("feed_wiring: gateway has no stream() — cannot subscribe %s", symbols)
        return

    for symbol in symbols:
        try:
            stream_fn(symbol=symbol, exchange=exchange, mode="LTP")
            logger.info("feed_wiring: subscribed %s on %s", symbol, exchange)
        except Exception as exc:
            logger.error("feed_wiring: failed to subscribe %s: %s", symbol, exc)


def _resolve_gateway(broker_service: Any) -> Any | None:
    """Return the active MarketDataGateway from BrokerService."""
    for attr in ("_gateway", "_upstox_gateway", "gateway"):
        gw = getattr(broker_service, attr, None)
        if gw is not None:
            return gw
    getter = getattr(broker_service, "get_gateway", None)
    if callable(getter):
        try:
            return getter()
        except Exception:
            pass
    return None
