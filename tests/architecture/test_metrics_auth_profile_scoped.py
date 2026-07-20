"""Architecture ratchet — metrics auth profile-scoped (SEC-004/005)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import interface.api.auth as auth
from interface.api.auth import _is_metrics_auth_gated


@pytest.fixture(autouse=True)
def _restore_auth_state():
    saved_mode = auth.AUTH_MODE
    saved_key = auth.API_KEY
    yield
    auth.AUTH_MODE = saved_mode
    auth.API_KEY = saved_key
    auth._AuthConfig.AUTH_MODE = saved_mode
    auth._AuthConfig.API_KEY = saved_key


def _health_client(
    monkeypatch,
    *,
    tradex_env: str = "development",
    auth_mode: str = "none",
    api_key: str = "",
    force_prod_validation: bool = False,
) -> TestClient:
    monkeypatch.setenv("TRADEX_ENV", tradex_env)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    if force_prod_validation:
        monkeypatch.setenv("TRADEX_FORCE_PROD_VALIDATION", "1")
    else:
        monkeypatch.delenv("TRADEX_FORCE_PROD_VALIDATION", raising=False)
    auth.configure(auth_mode=auth_mode, api_key=api_key)

    from interface.api.routers.health import router as health_router

    app = FastAPI()
    app.include_router(health_router, prefix="/api/v1/health")
    return TestClient(app)


def test_is_metrics_auth_gated_true_in_prod(monkeypatch) -> None:
    monkeypatch.setenv("TRADEX_ENV", "production")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("TRADEX_FORCE_PROD_VALIDATION", "1")
    assert _is_metrics_auth_gated() is True


def test_is_metrics_auth_gated_false_in_dev(monkeypatch) -> None:
    monkeypatch.setenv("TRADEX_ENV", "development")
    monkeypatch.delenv("TRADEX_FORCE_PROD_VALIDATION", raising=False)
    assert _is_metrics_auth_gated() is False


def test_prod_metrics_require_api_key(monkeypatch) -> None:
    """Production/staging metrics reject unauthenticated scrapes."""
    client = _health_client(
        monkeypatch,
        tradex_env="production",
        auth_mode="api_key",
        api_key="prod-metrics-secret",
        force_prod_validation=True,
    )

    for path in ("/api/v1/health/metrics", "/api/v1/health/metrics/prometheus"):
        unauth = client.get(path)
        assert unauth.status_code == 401
        assert "Missing API key" in unauth.json()["detail"]

        authed = client.get(path, headers={"X-API-Key": "prod-metrics-secret"})
        assert authed.status_code == 200


def test_dev_metrics_public_without_key(monkeypatch) -> None:
    """Development metrics stay public when AUTH_MODE=none (default)."""
    client = _health_client(monkeypatch, tradex_env="development", auth_mode="none")

    for path in ("/api/v1/health/metrics", "/api/v1/health/metrics/prometheus"):
        response = client.get(path)
        assert response.status_code == 200

    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/health/readyz").status_code in (200, 503)


def test_dev_metrics_public_even_when_api_key_mode(monkeypatch) -> None:
    """Metrics auth is profile-scoped — dev stays public even with AUTH_MODE=api_key."""
    client = _health_client(
        monkeypatch,
        tradex_env="development",
        auth_mode="api_key",
        api_key="dev-local-key",
    )

    for path in ("/api/v1/health/metrics", "/api/v1/health/metrics/prometheus"):
        response = client.get(path)
        assert response.status_code == 200, path


@pytest.mark.parametrize("tradex_env", ["production", "staging"])
def test_liveness_and_readiness_stay_public_in_prod(monkeypatch, tradex_env: str) -> None:
    """Probe endpoints must remain reachable without API key in prod/staging."""
    client = _health_client(
        monkeypatch,
        tradex_env=tradex_env,
        auth_mode="api_key",
        api_key="probe-test-key",
        force_prod_validation=True,
    )

    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/health/readyz").status_code in (200, 503)
