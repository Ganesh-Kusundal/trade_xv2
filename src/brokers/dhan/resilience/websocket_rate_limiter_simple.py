"""Simple WebSocket rate limiting for Dhan broker.

.. deprecated::
    This module is effectively DEAD and retained only for backwards
    compatibility. Its :meth:`SimpleWebSocketRateLimiter.can_create_depth_200_connection`
    counter (``_depth_200_connections``) is never incremented/decremented by any
    caller, so the gate always returns ``True``. The unbounded spin-wait that
    previously relied on it (in ``brokers.dhan.depth_200.Depth200ConnectionPool.get_feed``)
    could loop forever holding a lock and was removed.

    Connection-cap enforcement for depth-200 now lives in
    :class:`~brokers.dhan.depth_200.Depth200ConnectionPool` (``max_connections``
    eviction-by-oldest). Host-wide per-connection-type admission (including
    the 429 cooldown) is handled by
    :class:`~brokers.dhan.connection_admission.MarketFeedConnectionAdmission`.
    Do not introduce new callers of this module.
"""



from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class SimpleWebSocketRateLimiter:
    """Simple WebSocket rate limiter for Dhan connections.
    
    Provides basic rate limiting for WebSocket connections with:
    - Connection rate limiting using timestamps
    - Connection pool size management for depth-200 feeds
    """
    
    def __init__(self):
        """Initialize the simple WebSocket rate limiter."""
        self._lock = threading.Lock()
        
        # Connection rate limiting
        self._last_connection_time = 0.0
        self._min_connection_interval = 1.0  # 1 second between connections
        
        # Depth-200 connection pool tracking
        self._depth_200_connections = 0
        self._max_depth_200_connections = 5  # Dhan allows up to 5 concurrent WebSocket connections
        
        # Rate limit violation tracking
        self._connection_violations = 0
    
    def can_create_connection(self) -> bool:
        """Check if a new WebSocket connection can be created.
        
        Returns:
            True if a new connection can be created, False if rate limited
        """
        with self._lock:
            current_time = time.monotonic()
            time_since_last = current_time - self._last_connection_time
            
            if time_since_last >= self._min_connection_interval:
                self._last_connection_time = current_time
                return True
            else:
                self._connection_violations += 1
                logger.warning(
                    "websocket_connection_rate_limit_violation",
                    extra={
                        "violations": self._connection_violations,
                        "retry_after": self._min_connection_interval - time_since_last,
                    },
                )
                return False
    
    def can_create_depth_200_connection(self) -> bool:
        """Check if a new depth-200 connection can be created.
        
        Returns:
            True if a new depth-200 connection can be created, False if limit reached
        """
        with self._lock:
            if self._depth_200_connections < self._max_depth_200_connections:
                return True
            else:
                logger.warning(
                    "depth_200_connection_limit_reached",
                    extra={
                        "current_connections": self._depth_200_connections,
                        "max_connections": self._max_depth_200_connections,
                    },
                )
                return False
    
    def release_depth_200_connection(self) -> None:
        """Release a depth-200 connection slot."""
        with self._lock:
            if self._depth_200_connections > 0:
                self._depth_200_connections -= 1
    
    def get_connection_delay(self) -> float:
        """Get the delay until next connection can be created.
        
        Returns:
            Delay in seconds, or 0 if connection can be created immediately
        """
        with self._lock:
            current_time = time.monotonic()
            time_since_last = current_time - self._last_connection_time
            delay = self._min_connection_interval - time_since_last
            return max(0.0, delay)
    
    def get_stats(self) -> dict[str, Any]:
        """Get rate limiter statistics for monitoring.
        
        Returns:
            Dictionary with rate limiter statistics
        """
        with self._lock:
            return {
                "connections": {
                    "violations": self._connection_violations,
                    "delay_seconds": self.get_connection_delay(),
                },
                "depth_200": {
                    "current_connections": self._depth_200_connections,
                    "max_connections": self._max_depth_200_connections,
                },
            }
    
    def reset_violations(self) -> None:
        """Reset all rate limit violation counters."""
        with self._lock:
            self._connection_violations = 0


# Global WebSocket rate limiter instance for Dhan
_dhan_ws_rate_limiter: SimpleWebSocketRateLimiter | None = None
_dhan_ws_rate_limiter_lock = threading.Lock()


def get_dhan_ws_rate_limiter() -> SimpleWebSocketRateLimiter:
    """Get or create the global Dhan WebSocket rate limiter.
    
    Returns:
        Global SimpleWebSocketRateLimiter instance
    """
    global _dhan_ws_rate_limiter
    
    with _dhan_ws_rate_limiter_lock:
        if _dhan_ws_rate_limiter is None:
            _dhan_ws_rate_limiter = SimpleWebSocketRateLimiter()
        return _dhan_ws_rate_limiter


def reset_dhan_ws_rate_limiter() -> None:
    """Reset the global Dhan WebSocket rate limiter.
    
    Useful for testing or when you want to clear accumulated rate limit state.
    """
    global _dhan_ws_rate_limiter
    
    with _dhan_ws_rate_limiter_lock:
        if _dhan_ws_rate_limiter is not None:
            _dhan_ws_rate_limiter.reset_violations()