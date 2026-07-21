"""Upstox V3 WebSocket auto-reconnect — thin wrapper over kernel policy.

Defaults match the official Upstox SDK: ``auto_reconnect(True, 10, 3)``.
"""

from __future__ import annotations

from brokers.common.transport import ReconnectingTransport
from brokers.common.transport_policy import ResiliencePolicy


class UpstoxAutoReconnect:
    def __init__(
        self,
        enabled: bool = True,
        interval_seconds: float = 10.0,
        max_retries: int = 3,
        jitter: float = 0.2,
    ) -> None:
        self._enabled = enabled
        policy = ResiliencePolicy(
            base_delay_s=float(interval_seconds),
            max_delay_s=max(300.0, float(interval_seconds) * 32),
            max_attempts=int(max_retries),
            jitter=float(jitter),
        )
        self._transport = ReconnectingTransport(policy)

    def should_retry(self, attempt: int | None = None) -> bool:
        if not self._enabled:
            return False
        if attempt is not None:
            return self._transport.policy.should_retry(int(attempt))
        return self._transport.should_retry()

    def next_delay(self, attempt: int | None = None) -> float:
        if attempt is not None:
            return self._transport.policy.delay_for(int(attempt))
        return self._transport.next_delay()

    def reset(self) -> None:
        self._transport.reset()

    def record_failure(self) -> None:
        self._transport.record_failure()
