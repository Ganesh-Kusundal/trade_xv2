"""Backoff sequence parity across ResiliencePolicy / ReconnectingTransport."""

from __future__ import annotations

from brokers.common.transport import ReconnectingTransport
from brokers.common.transport_policy import ResiliencePolicy
from brokers.providers.upstox.websocket.v3_auto_reconnect import UpstoxAutoReconnect


def test_upstox_policy_matches_sdk_defaults():
    p = ResiliencePolicy.for_upstox_ws()
    assert p.base_delay_s == 10.0
    assert p.max_attempts == 3


def test_dhan_ws_policy_persistent():
    p = ResiliencePolicy.for_dhan_ws()
    assert p.max_attempts == 50
    assert p.cooloff_s == 60.0


def test_backoff_sequence_identical_for_same_policy():
    policy = ResiliencePolicy(base_delay_s=1.0, max_delay_s=30.0, max_attempts=5, jitter=0.0)
    a = ReconnectingTransport(policy)
    b = ReconnectingTransport(policy)
    delays_a = []
    delays_b = []
    for _ in range(4):
        delays_a.append(a.next_delay(with_jitter=False))
        delays_b.append(b.next_delay(with_jitter=False))
        a.record_failure()
        b.record_failure()
    assert delays_a == delays_b == [1.0, 2.0, 4.0, 8.0]


def test_upstox_auto_reconnect_uses_kernel_policy():
    ar = UpstoxAutoReconnect(interval_seconds=10.0, max_retries=3, jitter=0.0)
    assert ar.should_retry(0) is True
    assert ar.should_retry(3) is False
    assert ar.next_delay(0) == 10.0
    assert ar.next_delay(1) == 20.0
