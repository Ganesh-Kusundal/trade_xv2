"""CircuitBreakerHttpClient — circuit breaker wrapping HttpClient."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from plugins.brokers.common.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerHttpClient,
    CircuitBreakerOpenError,
    CircuitState,
)


class _FakeClient:
    """Injectable fake HttpClient for testing."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.status = 200
        self.body: Any = {"ok": True}
        self.exc: Exception | None = None

    def request(self, method: str, url: str, **kwargs: Any) -> tuple[int, Any]:
        self.calls.append((method, url, kwargs))
        if self.exc:
            raise self.exc
        return self.status, self.body


# --- Normal operation (closed state) ---


def test_closed_state_passes_through() -> None:
    client = _FakeClient()
    cb = CircuitBreakerHttpClient(client, CircuitBreakerConfig())
    status, body = cb.request("GET", "https://example.test/data")
    assert status == 200
    assert body == {"ok": True}
    assert cb._state == CircuitState.CLOSED


def test_closed_state_returns_response() -> None:
    client = _FakeClient()
    client.body = {"data": 42}
    cb = CircuitBreakerHttpClient(client, CircuitBreakerConfig())
    _, body = cb.request("POST", "https://example.test/submit", json={"x": 1})
    assert body == {"data": 42}
    assert client.calls[0][0] == "POST"


# --- Opening after N failures ---


def test_opens_after_failure_threshold() -> None:
    client = _FakeClient()
    client.exc = ConnectionError("network down")
    cb = CircuitBreakerHttpClient(client, CircuitBreakerConfig(failure_threshold=3))

    for _ in range(3):
        with pytest.raises(ConnectionError):
            cb.request("GET", "https://example.test/data")

    assert cb._state == CircuitState.OPEN
    assert cb._failure_count == 3


def test_does_not_open_before_threshold() -> None:
    client = _FakeClient()
    client.exc = ConnectionError("network down")
    cb = CircuitBreakerHttpClient(client, CircuitBreakerConfig(failure_threshold=5))

    for _ in range(4):
        with pytest.raises(ConnectionError):
            cb.request("GET", "https://example.test/data")

    assert cb._state == CircuitState.CLOSED
    assert cb._failure_count == 4


def test_failures_reset_on_success() -> None:
    client = _FakeClient()
    cb = CircuitBreakerHttpClient(client, CircuitBreakerConfig(failure_threshold=5))

    client.exc = ConnectionError("down")
    with pytest.raises(ConnectionError):
        cb.request("GET", "https://example.test/data")
    with pytest.raises(ConnectionError):
        cb.request("GET", "https://example.test/data")

    client.exc = None
    client.body = {"ok": True}
    cb.request("GET", "https://example.test/data")

    assert cb._failure_count == 0
    assert cb._state == CircuitState.CLOSED


# --- Rejecting when open ---


def test_open_circuit_rejects_request() -> None:
    client = _FakeClient()
    client.exc = ConnectionError("down")
    cb = CircuitBreakerHttpClient(client, CircuitBreakerConfig(failure_threshold=2))

    for _ in range(2):
        with pytest.raises(ConnectionError):
            cb.request("GET", "https://example.test/data")

    assert cb._state == CircuitState.OPEN

    with pytest.raises(CircuitBreakerOpenError, match="Circuit breaker is open"):
        cb.request("GET", "https://example.test/data")

    assert len(client.calls) == 2  # no new call


# --- Half-open after timeout ---


def test_half_open_after_timeout() -> None:
    client = _FakeClient()
    client.exc = ConnectionError("down")
    cb = CircuitBreakerHttpClient(
        client,
        CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.1),
    )

    for _ in range(2):
        with pytest.raises(ConnectionError):
            cb.request("GET", "https://example.test/data")

    assert cb._state == CircuitState.OPEN

    time.sleep(0.15)

    client.exc = None
    client.body = {"recovered": True}
    status, body = cb.request("GET", "https://example.test/data")

    assert status == 200
    assert body == {"recovered": True}
    assert cb._state == CircuitState.HALF_OPEN


def test_stays_open_before_timeout() -> None:
    client = _FakeClient()
    client.exc = ConnectionError("down")
    cb = CircuitBreakerHttpClient(
        client,
        CircuitBreakerConfig(failure_threshold=2, recovery_timeout=1.0),
    )

    for _ in range(2):
        with pytest.raises(ConnectionError):
            cb.request("GET", "https://example.test/data")

    with pytest.raises(CircuitBreakerOpenError):
        cb.request("GET", "https://example.test/data")


# --- Closing after success threshold ---


def test_closes_after_success_threshold_in_half_open() -> None:
    client = _FakeClient()
    client.exc = ConnectionError("down")
    cb = CircuitBreakerHttpClient(
        client,
        CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=0.05,
            success_threshold=3,
        ),
    )

    for _ in range(2):
        with pytest.raises(ConnectionError):
            cb.request("GET", "https://example.test/data")

    time.sleep(0.1)
    client.exc = None

    for _ in range(3):
        cb.request("GET", "https://example.test/data")

    assert cb._state == CircuitState.CLOSED
    assert cb._failure_count == 0


def test_half_open_failure_reopens() -> None:
    client = _FakeClient()
    client.exc = ConnectionError("down")
    cb = CircuitBreakerHttpClient(
        client,
        CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.05),
    )

    for _ in range(2):
        with pytest.raises(ConnectionError):
            cb.request("GET", "https://example.test/data")

    time.sleep(0.1)

    # Success to enter half-open
    client.exc = None
    cb.request("GET", "https://example.test/data")
    assert cb._state == CircuitState.HALF_OPEN

    # Failure reopens
    client.exc = ConnectionError("still down")
    with pytest.raises(ConnectionError):
        cb.request("GET", "https://example.test/data")

    assert cb._state == CircuitState.OPEN


# --- Default config ---


def test_default_config() -> None:
    client = _FakeClient()
    cb = CircuitBreakerHttpClient(client)
    assert cb._config.failure_threshold == 5
    assert cb._config.recovery_timeout == 30.0
    assert cb._config.success_threshold == 2


# --- Thread safety ---


def test_concurrent_requests_thread_safe() -> None:
    client = _FakeClient()
    cb = CircuitBreakerHttpClient(
        client,
        CircuitBreakerConfig(failure_threshold=100),
    )
    errors: list[Exception] = []

    def worker() -> None:
        try:
            cb.request("GET", "https://example.test/data")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert cb._state == CircuitState.CLOSED
    assert cb._failure_count == 0


def test_concurrent_failures_thread_safe() -> None:
    client = _FakeClient()
    client.exc = ConnectionError("down")
    cb = CircuitBreakerHttpClient(
        client,
        CircuitBreakerConfig(failure_threshold=100),
    )
    caught = 0

    def worker() -> None:
        nonlocal caught
        try:
            cb.request("GET", "https://example.test/data")
        except ConnectionError:
            caught += 1

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert caught == 20
    assert cb._failure_count == 20
