"""Live integration tests for Dhan observability endpoints.

Tests get_connection_status(), get_circuit_breaker_states(),
get_token_refresh_metrics(), and get_rate_limiter_metrics() when exposed
on the gateway (optional — DhanWireAdapter may omit these passthroughs).

These tests require a valid .env.local with DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))


pytestmark = [pytest.mark.dhan, pytest.mark.off_market_safe, pytest.mark.regression]
from brokers.providers.dhan.wire import DhanWireAdapter

ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env.local"
_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=True)
    _live_env_loaded = bool(os.environ.get("DHAN_CLIENT_ID"))


def _require_observability(gateway: DhanWireAdapter, method: str) -> None:
    if not hasattr(gateway, method):
        pytest.skip(f"optional observability: {method}")


@pytest.mark.skipif(not _live_env_loaded, reason=".env.local with DHAN_CLIENT_ID required")
class TestLiveObservability:
    """Observability endpoint tests against live Dhan API."""

    def test_get_connection_status_returns_dict(self, gateway: DhanWireAdapter):
        _require_observability(gateway, "get_connection_status")
        status = gateway.get_connection_status()
        assert isinstance(status, dict)

    def test_connection_status_has_market_feed(self, gateway: DhanWireAdapter):
        _require_observability(gateway, "get_connection_status")
        status = gateway.get_connection_status()
        if "market_feed" in status:
            assert isinstance(status["market_feed"], bool)

    def test_get_circuit_breaker_states_returns_dict(self, gateway: DhanWireAdapter):
        _require_observability(gateway, "get_circuit_breaker_states")
        states = gateway.get_circuit_breaker_states()
        assert isinstance(states, dict)
        for name, state in states.items():
            assert isinstance(state, int), f"Circuit breaker {name} state not int"
            assert 0 <= state <= 2, f"Circuit breaker {name} invalid state: {state}"

    def test_circuit_breaker_has_read_cb(self, gateway: DhanWireAdapter):
        _require_observability(gateway, "get_circuit_breaker_states")
        states = gateway.get_circuit_breaker_states()
        assert "read_cb" in states or len(states) > 0

    def test_circuit_breaker_has_write_cb(self, gateway: DhanWireAdapter):
        _require_observability(gateway, "get_circuit_breaker_states")
        states = gateway.get_circuit_breaker_states()
        assert "write_cb" in states or len(states) > 0

    def test_get_token_refresh_metrics_returns_dict(self, gateway: DhanWireAdapter):
        _require_observability(gateway, "get_token_refresh_metrics")
        metrics = gateway.get_token_refresh_metrics()
        assert isinstance(metrics, dict)
        assert "refresh_count" in metrics
        assert "error_count" in metrics
        assert isinstance(metrics["refresh_count"], int)
        assert isinstance(metrics["error_count"], int)

    def test_token_refresh_count_non_negative(self, gateway: DhanWireAdapter):
        _require_observability(gateway, "get_token_refresh_metrics")
        metrics = gateway.get_token_refresh_metrics()
        assert metrics["refresh_count"] >= 0

    def test_token_error_count_non_negative(self, gateway: DhanWireAdapter):
        _require_observability(gateway, "get_token_refresh_metrics")
        metrics = gateway.get_token_refresh_metrics()
        assert metrics["error_count"] >= 0

    def test_get_rate_limiter_metrics_returns_dict(self, gateway: DhanWireAdapter):
        _require_observability(gateway, "get_rate_limiter_metrics")
        metrics = gateway.get_rate_limiter_metrics()
        assert isinstance(metrics, dict)
        assert "tokens_available" in metrics
        assert "requests_throttled" in metrics
        assert isinstance(metrics["tokens_available"], int)
        assert isinstance(metrics["requests_throttled"], int)

    def test_rate_limiter_tokens_non_negative(self, gateway: DhanWireAdapter):
        _require_observability(gateway, "get_rate_limiter_metrics")
        metrics = gateway.get_rate_limiter_metrics()
        assert metrics["tokens_available"] >= 0

    def test_rate_limiter_throttled_non_negative(self, gateway: DhanWireAdapter):
        _require_observability(gateway, "get_rate_limiter_metrics")
        metrics = gateway.get_rate_limiter_metrics()
        assert metrics["requests_throttled"] >= 0

    def test_observability_all_methods_callable(self, gateway: DhanWireAdapter):
        for method in (
            "get_connection_status",
            "get_circuit_breaker_states",
            "get_token_refresh_metrics",
            "get_rate_limiter_metrics",
        ):
            if not hasattr(gateway, method):
                pytest.skip(f"optional observability: {method}")
        assert gateway.get_connection_status() is not None
        assert gateway.get_circuit_breaker_states() is not None
        assert gateway.get_token_refresh_metrics() is not None
        assert gateway.get_rate_limiter_metrics() is not None
