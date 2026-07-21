from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from brokers.providers.upstox.auth.config import UpstoxConnectionSettings
from brokers.providers.upstox.auth.http import UpstoxHttpClient
from infrastructure.resilience.circuit_breaker import CircuitBreaker, CircuitState


def test_4xx_does_not_open_circuit_breaker():
    settings = UpstoxConnectionSettings(client_id="CID")
    client = UpstoxHttpClient(
        token_provider=lambda: "TOK",
        settings=settings,
        session=MagicMock(),
    )
    cb = client._write_circuit_breaker
    assert cb is not None
    assert cb.state == CircuitState.CLOSED

    # Send 3 requests that all return 400 — CB should stay CLOSED
    for _ in range(3):
        resp = MagicMock()
        resp.status_code = 400
        resp.text = '{"status": "error", "errors": [{"message": "bad request"}]}'
        client._session.request.return_value = resp
        with pytest.raises(Exception):
            client.post_json("https://api.upstox.com/v2/order/place", {})

    assert cb.state == CircuitState.CLOSED, (
        f"Expected CLOSED after three 4xx, got {cb.state} "
        f"(failure_count={cb.metrics.failure_count})"
    )


def test_423_does_not_open_circuit_breaker():
    settings = UpstoxConnectionSettings(client_id="CID")
    client = UpstoxHttpClient(
        token_provider=lambda: "TOK",
        settings=settings,
        session=MagicMock(),
    )
    cb = client._write_circuit_breaker
    assert cb is not None
    assert cb.state == CircuitState.CLOSED

    # 3 requests that return 423 (maintenance) — CB should stay CLOSED
    for _ in range(3):
        resp = MagicMock()
        resp.status_code = 423
        resp.text = "Locked"
        client._session.request.return_value = resp
        with pytest.raises(Exception):
            client.post_json("https://api.upstox.com/v2/order/place", {})

    assert cb.state == CircuitState.CLOSED, (
        f"Expected CLOSED after three 423, got {cb.state}"
    )


def test_network_error_opens_circuit_breaker():
    settings = UpstoxConnectionSettings(client_id="CID")
    client = UpstoxHttpClient(
        token_provider=lambda: "TOK",
        settings=settings,
        session=MagicMock(),
    )
    cb = client._write_circuit_breaker
    assert cb is not None
    assert cb.state == CircuitState.CLOSED

    # Simulate a network error (transport failure)
    client._session.request.side_effect = requests.ConnectionError("connection refused")

    with pytest.raises(Exception):
        client.post_json("https://api.upstox.com/v2/order/place", {})

    assert cb.metrics.failure_count == 1, (
        f"Expected failure_count=1, got {cb.metrics.failure_count}"
    )
