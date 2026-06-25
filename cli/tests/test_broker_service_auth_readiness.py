"""BrokerService fail-closed behavior for authenticated readiness."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brokers.common.connection.bootstrap_result import BootstrapResult, BootstrapStatus
from brokers.common.connection.errors import BrokerNotReadyError


def test_live_actionable_false_when_auth_probe_fails(monkeypatch, tmp_path):
    env = tmp_path / ".env.local"
    env.write_text("DHAN_CLIENT_ID=ABC\nDHAN_ACCESS_TOKEN=TOK\n")
    monkeypatch.setattr("cli.services.broker_service._ENV_PATH", env)

    def failing_bootstrap(broker, **kwargs):
        return BootstrapResult(
            status=BootstrapStatus.REAUTH_REQUIRED,
            broker=broker,
            gateway=None,
            error="DH-906 after refresh",
            probe_passed=True,
            authenticated=False,
            probe_name="dhan.funds",
        )

    monkeypatch.setattr("cli.services.broker_service.bootstrap_gateway", failing_bootstrap)
    monkeypatch.setattr(
        "cli.services.broker_service.start_http_observability", lambda *a, **k: None
    )

    from cli.services.broker_service import BrokerService

    bs = BrokerService()
    bs._ensure_initialized()
    assert bs._gateway is None
    assert bs.dhan_load_error is not None
    assert bs.live_actionable is False


def test_lifecycle_not_started_when_auth_fails(monkeypatch, tmp_path):
    env = tmp_path / ".env.local"
    env.write_text("DHAN_CLIENT_ID=ABC\nDHAN_ACCESS_TOKEN=TOK\n")
    monkeypatch.setattr("cli.services.broker_service._ENV_PATH", env)

    started = {"count": 0}

    def failing_bootstrap(broker, **kwargs):
        return BootstrapResult(
            status=BootstrapStatus.REAUTH_REQUIRED,
            broker=broker,
            gateway=MagicMock(),
            error="token rejected",
            authenticated=False,
        )

    monkeypatch.setattr("cli.services.broker_service.bootstrap_gateway", failing_bootstrap)

    from cli.services.broker_service import BrokerService

    bs = BrokerService()
    real_start = bs._lifecycle.start_all

    def tracked_start():
        started["count"] += 1
        return real_start()

    monkeypatch.setattr(bs._lifecycle, "start_all", tracked_start)
    bs._ensure_initialized()
    assert started["count"] == 0


def test_active_broker_raises_when_dhan_bootstrap_fails(monkeypatch, tmp_path):
    env = tmp_path / ".env.local"
    env.write_text("DHAN_CLIENT_ID=ABC\nDHAN_ACCESS_TOKEN=TOK\n")
    monkeypatch.setattr("cli.services.broker_service._ENV_PATH", env)

    bootstrap = BootstrapResult(
        status=BootstrapStatus.REAUTH_REQUIRED,
        broker="dhan",
        gateway=None,
        error="DH-906 after refresh",
        authenticated=False,
        probe_name="dhan.funds",
    )

    monkeypatch.setattr(
        "cli.services.broker_service.bootstrap_gateway",
        lambda broker, **kwargs: bootstrap,
    )

    from cli.services.broker_service import BrokerService

    bs = BrokerService()
    bs._ensure_initialized()

    with pytest.raises(BrokerNotReadyError) as exc_info:
        _ = bs.active_broker

    err = exc_info.value
    assert err.broker == "dhan"
    assert err.status == BootstrapStatus.REAUTH_REQUIRED
    assert err.bootstrap is bootstrap
    assert "DH-906" in str(err)


def test_active_broker_raises_for_upstox_when_selected_and_unavailable(
    monkeypatch,
    tmp_path,
):
    env = tmp_path / ".env.local"
    env.write_text("DHAN_CLIENT_ID=ABC\nDHAN_ACCESS_TOKEN=TOK\n")
    upstox_env = tmp_path / ".env.upstox"
    upstox_env.write_text("UPSTOX_CLIENT_ID=UP\nUPSTOX_ACCESS_TOKEN=TOK\n")
    monkeypatch.setattr("cli.services.broker_service._ENV_PATH", env)

    upstox_bootstrap = BootstrapResult(
        status=BootstrapStatus.REAUTH_REQUIRED,
        broker="upstox",
        gateway=None,
        error="Upstox token expired",
        authenticated=False,
    )

    def bootstrap_side_effect(broker, **kwargs):
        if broker == "dhan":
            return BootstrapResult(
                status=BootstrapStatus.REAUTH_REQUIRED,
                broker="dhan",
                gateway=None,
                error="Dhan token rejected",
                authenticated=False,
            )
        return upstox_bootstrap

    monkeypatch.setattr(
        "cli.services.broker_service.bootstrap_gateway",
        bootstrap_side_effect,
    )
    monkeypatch.setattr(
        "cli.services.broker_service.resolve_env_path",
        lambda broker, default=None: upstox_env if broker == "upstox" else env,
    )

    from cli.services.broker_service import BrokerService

    bs = BrokerService()
    bs._ensure_initialized()
    bs._active_name = "upstox"

    with pytest.raises(BrokerNotReadyError) as exc_info:
        _ = bs.active_broker

    assert exc_info.value.broker == "upstox"
    assert exc_info.value.status == BootstrapStatus.REAUTH_REQUIRED
    assert exc_info.value.bootstrap is upstox_bootstrap


def test_active_broker_returns_upstox_oms_proxy_when_configured(monkeypatch, tmp_path):
    env = tmp_path / ".env.local"
    env.write_text("DHAN_CLIENT_ID=ABC\nDHAN_ACCESS_TOKEN=TOK\n")
    monkeypatch.setattr("cli.services.broker_service._ENV_PATH", env)

    upstox_gw = MagicMock()
    upstox_proxy = MagicMock()
    dhan_gw = MagicMock()
    dhan_proxy = MagicMock()

    from cli.services.broker_service import BrokerService

    bs = BrokerService()
    bs._initialized = True
    bs._live_intent = True
    bs._gateway = dhan_gw
    bs._oms_proxy = dhan_proxy
    bs._upstox_gateway = upstox_gw
    bs._upstox_oms_proxy = upstox_proxy
    bs._active_name = "upstox"

    assert bs.active_broker is upstox_proxy
    bs._active_name = "dhan"
    assert bs.active_broker is dhan_proxy
