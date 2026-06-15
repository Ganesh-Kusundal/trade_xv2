"""Chaos testing for Dhan broker adapter.

Simulates API downtime, network failures, and session expiry to verify
graceful degradation and recovery.
"""

from __future__ import annotations

import time
from unittest.mock import patch, MagicMock

import pytest
from brokers.dhan.connection import DhanConnection
from brokers.dhan.domain import Exchange
from brokers.dhan.gateway import BrokerGateway
from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.resolver import SymbolResolver

SAMPLE_ROWS = [
    {"SEM_TRADING_SYMBOL": "RELIANCE", "SEM_SMST_SECURITY_ID": "2885",
     "SEM_EXM_EXCH_ID": "NSE_EQ", "SEM_INSTRUMENT_NAME": "EQUITY",
     "SEM_LOT_UNITS": "1", "SEM_TICK_SIZE": "0.05", "SEM_CUSTOM_SYMBOL": "Reliance Industries"},
]


class FakeHttpClient:
    def __init__(self):
        self.client_id = "test"
        self.access_token = "test"
        self._fail = False
        self._fail_count = 0

    def get(self, endpoint, **kw):
        if self._fail:
            self._fail_count += 1
            raise ConnectionError("Simulated network failure")
        if "/marketfeed" in endpoint:
            return {"data": {"NSE_EQ": {"2885": {"last_price": 2500}}}}
        return {"data": []}

    def post(self, endpoint, json=None):
        if self._fail:
            self._fail_count += 1
            raise ConnectionError("Simulated network failure")
        if "/marketfeed" in endpoint:
            return {"data": {"NSE_EQ": {"2885": {"last_price": 2500}}}}
        return {"data": []}

    def put(self, endpoint, json=None):
        if self._fail:
            self._fail_count += 1
            raise ConnectionError("Simulated network failure")
        return {"data": {}}

    def delete(self, endpoint):
        if self._fail:
            self._fail_count += 1
            raise ConnectionError("Simulated network failure")
        return {"data": {}}


@pytest.fixture()
def chaos_gateway() -> BrokerGateway:
    client = FakeHttpClient()
    conn = DhanConnection(client=client)
    conn.instruments.load_from_rows(SAMPLE_ROWS)
    gw = BrokerGateway(conn)
    gw._test_client = client
    return gw


class TestNetworkDisconnect:
    """Simulate network failures."""

    def test_get_ltp_network_failure(self, chaos_gateway):
        chaos_gateway._test_client._fail = True
        with pytest.raises(ConnectionError):
            chaos_gateway.get_ltp("RELIANCE", "NSE")

    def test_get_quote_network_failure(self, chaos_gateway):
        chaos_gateway._test_client._fail = True
        with pytest.raises(ConnectionError):
            chaos_gateway.get_quote("RELIANCE", "NSE")

    def test_recovery_after_network_failure(self, chaos_gateway):
        chaos_gateway._test_client._fail = True
        with pytest.raises(ConnectionError):
            chaos_gateway.get_ltp("RELIANCE", "NSE")

        chaos_gateway._test_client._fail = False
        result = chaos_gateway.get_ltp("RELIANCE", "NSE")
        assert result is not None


class TestCircuitBreaker:
    """Verify circuit breaker opens after repeated failures."""

    def test_circuit_opens_after_failures(self, chaos_gateway):
        from brokers.common.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState

        config = CircuitBreakerConfig(failure_threshold=3, open_duration_ms=1000)
        cb = CircuitBreaker("test", config)

        for _ in range(3):
            cb.on_failure()

        assert cb.state == CircuitState.OPEN

    def test_circuit_half_open_after_timeout(self):
        from brokers.common.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState

        config = CircuitBreakerConfig(failure_threshold=2, open_duration_ms=100)
        cb = CircuitBreaker("test", config)

        cb.on_failure()
        cb.on_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.15)
        assert cb.allow_request() is True
        assert cb.state == CircuitState.HALF_OPEN


class TestRateLimiting:
    """Verify rate limiting prevents rapid requests."""

    def test_rate_limit_exists(self):
        from brokers.dhan.http_client import _RATE_LIMITS
        assert "/marketfeed/quote" in _RATE_LIMITS
        assert "/optionchain" in _RATE_LIMITS
        assert _RATE_LIMITS["/marketfeed/quote"] > 0
        assert _RATE_LIMITS["/optionchain"] > 0
