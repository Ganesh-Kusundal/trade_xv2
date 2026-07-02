"""Wire WebSocket market subscriptions to the active broker gateway."""

from __future__ import annotations

import contextlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Tracks API-client-driven subscriptions for symmetric unstream on disconnect.
_api_subscriptions: dict[str, tuple[str, str]] = {}


def subscribe_symbols_to_broker(symbols: list[str], exchange: str = "NSE") -> None:
    """Subscribe *symbols* on the live broker gateway so ticks reach the EventBus.

    Called when API WebSocket clients subscribe to market data. Uses the
    broker gateway's ``stream()`` method which deduplicates subscriptions.
    Also subscribes to depth feeds when available.
    """
    if not symbols:
        return

    try:
        from api.deps import get_container

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
    if stream_fn is not None:
        for symbol in symbols:
            try:
                stream_fn(symbol=symbol, exchange=exchange, mode="FULL")
                _api_subscriptions[f"{symbol}:{exchange}"] = (symbol, exchange)
                logger.info("feed_wiring: subscribed %s on %s (FULL mode)", symbol, exchange)
            except Exception as exc:
                logger.error("feed_wiring: failed to subscribe %s: %s", symbol, exc)

    depth_fn = getattr(gateway, "depth_20", None)
    if depth_fn is not None:
        for symbol in symbols:
            try:
                depth_fn(symbol=symbol, exchange=exchange)
                logger.info("feed_wiring: subscribed depth_20 for %s", symbol)
            except Exception as exc:
                logger.debug("feed_wiring: depth_20 subscribe failed for %s: %s", symbol, exc)


def unsubscribe_symbols_from_broker(symbols: list[str], exchange: str = "NSE") -> None:
    """Unsubscribe *symbols* when API WebSocket clients disconnect."""
    if not symbols:
        return

    try:
        from api.deps import get_container

        container = get_container()
    except Exception:
        logger.debug("feed_wiring: service container unavailable")
        return

    broker_service = container.broker_service
    if broker_service is None:
        return

    gateway = _resolve_gateway(broker_service)
    if gateway is None:
        return

    unstream_fn = getattr(gateway, "unstream", None)
    if unstream_fn is None:
        return

    for symbol in symbols:
        key = f"{symbol}:{exchange}"
        _api_subscriptions.pop(key, None)
        try:
            unstream_fn(symbol=symbol, exchange=exchange)
            logger.info("feed_wiring: unsubscribed %s on %s", symbol, exchange)
        except Exception as exc:
            logger.debug("feed_wiring: unstream failed for %s: %s", symbol, exc)


def _resolve_gateway(broker_service: Any) -> Any | None:
    """Return the active MarketDataGateway from BrokerService."""
    getter = getattr(broker_service, "active_gateway", None)
    if getter is not None:
        return getter
    for attr in ("_gateway", "_upstox_gateway", "gateway"):
        gw = getattr(broker_service, attr, None)
        if gw is not None:
            return gw
    getter = getattr(broker_service, "get_gateway", None)
    if callable(getter):
        with contextlib.suppress(Exception):
            return getter()
    return None
