from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brokers.upstox.auth.config import UpstoxConnectionSettings
from brokers.upstox.auth.exceptions import UpstoxApiError, UpstoxFundsMaintenanceError
from brokers.upstox.auth.http import UpstoxHttpClient


def test_http_client_injects_bearer_and_algo_name():
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.text = '{"status": "success", "data": {}}'
    session.request.return_value = resp
    settings = UpstoxConnectionSettings(client_id="CID", access_token="", algo_name="my-algo")
    client = UpstoxHttpClient(token_provider=lambda: "TOK", settings=settings, session=session)
    client.get_json("https://api.upstox.com/v2/user/profile")
    headers = session.request.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer TOK"
    assert headers["X-Algo-Name"] == "my-algo"
    assert session.request.call_args.kwargs["method"] == "GET"


def test_http_client_raises_on_4xx():
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 401
    resp.text = "unauthorized"
    session.request.return_value = resp
    settings = UpstoxConnectionSettings(client_id="CID")
    client = UpstoxHttpClient(token_provider=lambda: "TOK", settings=settings, session=session)
    with pytest.raises(UpstoxApiError) as excinfo:
        client.get_json("https://api.upstox.com/v2/user/profile")
    assert excinfo.value.status_code == 401


def test_http_client_raises_on_error_status_in_body():
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.text = '{"status": "error", "errors": [{"message": "bad price"}]}'
    resp.json.return_value = {
        "status": "error",
        "errors": [{"message": "bad price"}],
    }
    session.request.return_value = resp
    settings = UpstoxConnectionSettings(client_id="CID")
    client = UpstoxHttpClient(token_provider=lambda: "TOK", settings=settings, session=session)
    with pytest.raises(UpstoxApiError) as excinfo:
        client.get_json("https://api.upstox.com/v2/order/place")
    assert "bad price" in str(excinfo.value)


def test_http_client_does_not_send_algo_header_when_blank():
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.text = '{"status": "success", "data": {}}'
    session.request.return_value = resp
    settings = UpstoxConnectionSettings(client_id="CID", algo_name="")
    client = UpstoxHttpClient(token_provider=lambda: "TOK", settings=settings, session=session)
    client.get_json("https://api.upstox.com/v2/user/profile")
    headers = session.request.call_args.kwargs["headers"]
    assert "X-Algo-Name" not in headers


def test_enable_retry_removed():
    """enable_retry parameter was removed (no callers, pre-v1.0)."""
    session = MagicMock()
    settings = UpstoxConnectionSettings(client_id="CID")
    with pytest.raises(TypeError):
        UpstoxHttpClient(
            token_provider=lambda: "TOK",
            settings=settings,
            session=session,
            enable_retry=True,
        )


def test_read_circuit_breaker_does_not_block_write():
    from infrastructure.resilience.circuit_breaker import CircuitState
    from infrastructure.resilience.errors import CircuitBreakerOpenError

    session = MagicMock()
    settings = UpstoxConnectionSettings(client_id="CID")
    client = UpstoxHttpClient(
        token_provider=lambda: "TOK",
        settings=settings,
        session=session,
    )
    assert client._read_circuit_breaker is not None
    assert client._write_circuit_breaker is not None
    for _ in range(12):
        client._read_circuit_breaker.on_failure()
    assert client._read_circuit_breaker.state == CircuitState.OPEN

    resp = MagicMock()
    resp.status_code = 200
    resp.text = '{"status": "success", "data": {}}'
    session.request.return_value = resp

    client.post_json(
        "https://api.upstox.com/v2/order/place",
        {"quantity": 1},
    )
    session.request.assert_called_once()
    assert client._write_circuit_breaker.state != CircuitState.OPEN

    with pytest.raises(CircuitBreakerOpenError):
        client.get_json("https://api.upstox.com/v2/market-quote/ltp")


def test_default_rate_limiter_is_multi_bucket():
    from infrastructure.resilience.rate_limiter import MultiBucketRateLimiter

    session = MagicMock()
    settings = UpstoxConnectionSettings(client_id="CID")
    client = UpstoxHttpClient(
        token_provider=lambda: "TOK", settings=settings, session=session
    )
    assert isinstance(client.rate_limiter, MultiBucketRateLimiter)
    cats = set(client.rate_limiter.categories())
    # Capability profiles + admin catch-all + legacy aliases
    for required in (
        "orders",
        "quotes",
        "historical",
        "option_chain",
        "funds",
        "positions",
        "holdings",
        "admin",
    ):
        assert required in cats


def test_rate_limit_bucket_mapping():
    from brokers.upstox.auth.http import _rate_limit_bucket

    assert _rate_limit_bucket("https://api.upstox.com/v2/market-quote/ltp") == "quotes"
    assert _rate_limit_bucket("https://api.upstox.com/v2/market-quote/ohlc") == "quotes"
    assert _rate_limit_bucket("https://api.upstox.com/v2/historical/candle") == "historical"
    assert _rate_limit_bucket("https://api.upstox.com/v2/order/place") == "orders"
    assert _rate_limit_bucket("https://api.upstox.com/v2/order/book") == "orders"
    assert _rate_limit_bucket("https://api.upstox.com/v2/portfolio/long-term-holdings") == "holdings"
    assert _rate_limit_bucket("https://api.upstox.com/v2/portfolio/short-term-positions") == "positions"
    assert _rate_limit_bucket("https://api.upstox.com/v2/user/get-funds-and-margin") == "funds"
    assert _rate_limit_bucket("https://api.upstox.com/v3/user/get-funds-and-margin") == "funds"
    assert _rate_limit_bucket("https://api.upstox.com/v2/user/profile") == "admin"


def test_http_client_injects_api_version_for_v3():
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.text = '{"status": "success", "data": {}}'
    session.request.return_value = resp
    settings = UpstoxConnectionSettings(client_id="CID")
    client = UpstoxHttpClient(token_provider=lambda: "TOK", settings=settings, session=session)
    client.get_json("https://api.upstox.com/v3/user/get-funds-and-margin")
    headers = session.request.call_args.kwargs["headers"]
    assert headers["Api-Version"] == "3.0"


def test_http_client_raises_funds_maintenance_on_423():
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 423
    resp.text = "Locked"
    session.request.return_value = resp
    settings = UpstoxConnectionSettings(client_id="CID")
    client = UpstoxHttpClient(token_provider=lambda: "TOK", settings=settings, session=session)
    with pytest.raises(UpstoxFundsMaintenanceError) as excinfo:
        client.get_json("https://api.upstox.com/v3/user/get-funds-and-margin")
    assert excinfo.value.status_code == 423


def test_funds_url_points_to_v3():
    from config.endpoints import Upstox

    urls = Upstox.production()
    assert urls.funds_url() == "https://api.upstox.com/v3/user/get-funds-and-margin"
