"""Market depth provider for Dhan.

Provides 20-level market depth data for instruments.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from brokers.common.core.enums import ExchangeSegment
from brokers.common.core.models import MarketDepth, MarketDepthLevel
from brokers.common.resilience.retry import RetryExecutor
from brokers.dhan.websocket.market_data import DhanMarketFeedWebSocketClient


class DhanMarketDepthProvider:
    """Market depth provider for Dhan with 20-level support.

    Provides real-time market depth data with 20 bid/ask levels.
    """

    def __init__(
        self,
        http_client: Any,
        settings: Any,
        url_resolver: Any,
        retry_executor: RetryExecutor,
        websocket_client: DhanMarketFeedWebSocketClient | None = None,
    ) -> None:
        self._http_client = http_client
        self._settings = settings
        self._url_resolver = url_resolver
        self._retry_executor = retry_executor
        self._websocket_client = websocket_client

        # Cache for depth data
        self._depth_cache: dict[str, dict[str, Any]] = {}
        self._cache_ttl = 5  # seconds

    def get_depth(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
        use_websocket: bool = True,
    ) -> MarketDepth:
        """Get market depth for an instrument.

        Args:
            security_id: The security ID
            exchange_segment: The exchange segment
            use_websocket: Whether to use WebSocket for real-time data

        Returns:
            MarketDepth object with bid/ask levels
        """
        cache_key = f"{security_id}:{exchange_segment.value}"

        # Check cache first
        if use_websocket and self._websocket_client and self._websocket_client.is_connected():
            # Try to get from WebSocket
            depth = self._get_depth_from_websocket(security_id, exchange_segment)
            if depth:
                return depth

        # Fall back to REST API
        depth = self._get_depth_from_rest(security_id, exchange_segment)

        # Update cache
        if depth:
            self._depth_cache[cache_key] = {
                "depth": depth,
                "timestamp": datetime.now(),
            }

        return depth

    def _get_depth_from_rest(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
    ) -> MarketDepth:
        """Get depth from REST API."""
        response = self._retry_executor.execute(
            lambda: self._http_client.post_json(
                self._url_resolver.market_feed_quote_url(),
                {exchange_segment.value: [security_id]},
            )
        )
        return self._parse_depth_response(response, security_id, exchange_segment)

    def _get_depth_from_websocket(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
    ) -> MarketDepth | None:
        """Get depth from WebSocket."""
        if not self._websocket_client:
            return None

        # In a real implementation, this would subscribe to depth updates
        # For now, fall back to REST API
        return None

    def _parse_depth_response(
        self,
        response: dict[str, Any],
        security_id: str,
        exchange_segment: ExchangeSegment,
    ) -> MarketDepth:
        """Parse depth response into MarketDepth object."""
        from brokers.dhan.mapper.mapping import quote_payload_from_response

        data = quote_payload_from_response(response, security_id)
        raw_depth = data.get("depth") or data.get("marketDepth") or {}

        bids = []
        asks = []

        # Parse bid levels (up to 20 levels)
        for level in raw_depth.get("buy", [])[:20]:
            bids.append(
                MarketDepthLevel(
                    price=Decimal(str(level.get("price") or level.get("buyPrice") or 0)),
                    quantity=int(level.get("quantity") or level.get("qty") or 0),
                    orders=int(level.get("orders") or level.get("orderCount") or 0),
                )
            )

        # Parse ask levels (up to 20 levels)
        for level in raw_depth.get("sell", [])[:20]:
            asks.append(
                MarketDepthLevel(
                    price=Decimal(str(level.get("price") or level.get("sellPrice") or 0)),
                    quantity=int(level.get("quantity") or level.get("qty") or 0),
                    orders=int(level.get("orders") or level.get("orderCount") or 0),
                )
            )

        return MarketDepth(
            exchange_segment=exchange_segment,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(),
        )

    def subscribe_depth(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
    ) -> bool:
        """Subscribe to depth updates via WebSocket."""
        if self._websocket_client:
            return self._websocket_client.subscribe(
                security_id=security_id,
                exchange_segment=exchange_segment,
                feed_mode="depth",
            )
        return False

    def unsubscribe_depth(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
    ) -> bool:
        """Unsubscribe from depth updates via WebSocket."""
        if self._websocket_client:
            return self._websocket_client.unsubscribe(security_id, exchange_segment)
        return False

    def get_cached_depth(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
    ) -> MarketDepth | None:
        """Get cached depth if available and not stale."""
        cache_key = f"{security_id}:{exchange_segment.value}"
        cached = self._depth_cache.get(cache_key)

        if cached:
            age = (datetime.now() - cached["timestamp"]).total_seconds()
            if age < self._cache_ttl:
                return cached["depth"]

        return None

    def clear_cache(self) -> None:
        """Clear depth cache."""
        self._depth_cache.clear()
