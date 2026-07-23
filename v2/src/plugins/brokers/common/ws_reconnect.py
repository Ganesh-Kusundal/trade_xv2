"""WebSocket auto-reconnect with subscription replay."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ReconnectConfig:
    """Configuration for WebSocket reconnection behavior."""

    max_retries: int = 10
    base_delay: float = 1.0  # seconds
    max_delay: float = 30.0
    exponential_base: float = 2.0


class WsReconnectManager:
    """Manages WebSocket reconnection with subscription replay."""

    def __init__(self, config: ReconnectConfig | None = None) -> None:
        self._config = config or ReconnectConfig()
        self._retry_count = 0
        self._connected = False
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._connected

    def on_connect(self) -> None:
        """Called when WebSocket connects successfully."""
        with self._lock:
            self._retry_count = 0
            self._connected = True

    def on_close(self) -> None:
        """Called when WebSocket closes."""
        with self._lock:
            self._connected = False

    def on_disconnect(
        self,
        reconnect_fn: Callable[[], Any],
        replay_fn: Callable[[], None],
    ) -> None:
        """Called when WS disconnects. Runs reconnect loop.

        Args:
            reconnect_fn: Function to recreate the WebSocket connection.
            replay_fn: Function to replay all subscriptions after reconnect.
        """
        while self._retry_count < self._config.max_retries:
            delay = min(
                self._config.base_delay * (self._config.exponential_base**self._retry_count),
                self._config.max_delay,
            )
            time.sleep(delay)
            try:
                reconnect_fn()
                replay_fn()
                with self._lock:
                    self._retry_count = 0
                    self._connected = True
                return
            except Exception:
                with self._lock:
                    self._retry_count += 1

    def reset(self) -> None:
        """Reset retry counter and connection state."""
        with self._lock:
            self._retry_count = 0
            self._connected = False
