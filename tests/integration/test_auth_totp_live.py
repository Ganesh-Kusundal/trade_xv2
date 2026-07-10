"""Live auth integration — real TOTP bootstrap against broker APIs.

Runs automatically when credentials are configured in ``.env.local`` /
``.env.upstox``. Skips cleanly when not configured (CI default).

Run locally:
    venv/bin/python -m pytest tests/integration/test_auth_totp_live.py -v

Run with explicit opt-in (pre-prod / release gate):
    PRE_PROD_GATE=1 venv/bin/python -m pytest tests/integration/test_auth_totp_live.py -v
"""

from __future__ import annotations

import os

import pytest

from infrastructure.auth.environment_bootstrap import bootstrap_environment
from infrastructure.connection.bootstrap_result import BootstrapStatus
from tests.integration.auth_gates import (
    REPO_ROOT,
    dhan_readonly_gate,
    dhan_totp_gate,
    upstox_totp_gate,
)

_DHAN_TOTP = dhan_totp_gate()
_UPSTOX_TOTP = upstox_totp_gate()
_DHAN_RO = dhan_readonly_gate()


pytestmark = [
    pytest.mark.integration,
    pytest.mark.live_readonly,
    pytest.mark.auth_integration,
]


@pytest.mark.skipif(
    not _DHAN_TOTP.configured, reason=_DHAN_TOTP.reason or "Dhan TOTP not configured"
)
class TestDhanTotpLive:
    def test_environment_bootstrap_loads_dhan_env(self):
        loaded = bootstrap_environment(project_root=REPO_ROOT, brokers=("dhan",))
        assert loaded["dhan"] == _DHAN_TOTP.env_path
        assert os.environ.get("DHAN_CLIENT_ID")

    def test_bootstrap_gateway_authenticated_when_totp_configured(self):
        from interface.ui.services.broker_registry import bootstrap_gateway

        result = bootstrap_gateway(
            "dhan",
            env_path=_DHAN_TOTP.env_path,
            load_instruments=False,
            require_authenticated=True,
        )
        try:
            assert result.status in (BootstrapStatus.READY, BootstrapStatus.DEGRADED)
            assert result.live_ready, (
                f"expected live_ready: status={result.status.value} "
                f"error={result.error} probe={result.probe_name}"
            )
            assert result.authenticated
            assert result.gateway is not None
            assert result.probe_name
        finally:
            if result.gateway is not None:
                result.gateway.close()


@pytest.mark.skipif(
    not _UPSTOX_TOTP.configured, reason=_UPSTOX_TOTP.reason or "Upstox TOTP not configured"
)
class TestUpstoxTotpLive:
    def test_environment_bootstrap_loads_upstox_env(self):
        loaded = bootstrap_environment(project_root=REPO_ROOT, brokers=("upstox",))
        assert loaded["upstox"] == _UPSTOX_TOTP.env_path
        assert os.environ.get("UPSTOX_CLIENT_ID") or os.environ.get("UPSTOX_API_KEY")

    def test_token_manager_bootstrap_via_real_totp(self):
        from brokers.upstox.auth.config import UpstoxSettingsLoader
        from brokers.upstox.auth.token_manager import UpstoxTokenManager

        settings = UpstoxSettingsLoader.from_env(env_path=_UPSTOX_TOTP.env_path)
        assert settings.is_totp

        manager = UpstoxTokenManager(settings)
        state = manager.bootstrap()

        assert state.access_token
        assert len(state.access_token) > 20
        assert manager.bearer_token()

    def test_bootstrap_gateway_authenticated_when_totp_configured(self):
        from interface.ui.services.broker_registry import bootstrap_gateway

        result = bootstrap_gateway(
            "upstox",
            env_path=_UPSTOX_TOTP.env_path,
            load_instruments=False,
            require_authenticated=True,
        )
        try:
            assert result.live_ready, (
                f"expected live_ready: status={result.status.value} "
                f"error={result.error} probe={result.probe_name}"
            )
            assert result.authenticated
            assert result.gateway is not None
        finally:
            if result.gateway is not None:
                result.gateway.close()


@pytest.mark.skipif(
    not _DHAN_RO.configured, reason=_DHAN_RO.reason or "Dhan readonly creds missing"
)
class TestDhanBootstrapReadonlyLive:
    """Verify bootstrap + auth probe with an existing token (no forced TOTP)."""

    def test_bootstrap_reuses_valid_token_without_refresh(self):
        from interface.ui.services.broker_registry import bootstrap_gateway

        result = bootstrap_gateway(
            "dhan",
            env_path=_DHAN_RO.env_path,
            load_instruments=False,
            require_authenticated=True,
        )
        try:
            assert result.live_ready, result.error or result.status.value
            # When token is still valid, bootstrap must not force TOTP refresh.
            assert result.refreshed_token is False
        finally:
            if result.gateway is not None:
                result.gateway.close()
