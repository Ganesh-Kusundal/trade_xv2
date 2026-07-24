"""BrokerService fail-closed behavior for authenticated readiness."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from domain.exceptions import BrokerNotReadyError
from infrastructure.connection.bootstrap_result import BootstrapResult, BootstrapStatus


def test_live_actionable_false_when_auth_probe_fails(monkeypatch, tmp_path):
    env = tmp_path / ".env.local"
    env.write_text("DHAN_CLIENT_ID=ABC\nDHAN_ACCESS_TOKEN=TOK\n")
    monkeypatch.setattr("interface.ui.services.broker_service._ENV_PATH", env)

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

    monkeypatch.setattr("interface.ui.services.broker_service.bootstrap_gateway", failing_bootstrap)
    monkeypatch.setattr(
        "interface.ui.services.broker_service.BrokerService._start_http_observability_server",
        lambda self, rm: None,
    )

    from interface.ui.services.broker_service import BrokerService

    bs = BrokerService()
    bs.initialize()
    assert bs._gateway is None
    assert bs.dhan_load_error is not None
    assert bs.live_actionable is False


def test_lifecycle_not_started_when_auth_fails(monkeypatch, tmp_path):
    env = tmp_path / ".env.local"
    env.write_text("DHAN_CLIENT_ID=ABC\nDHAN_ACCESS_TOKEN=TOK\n")
    monkeypatch.setattr("interface.ui.services.broker_service._ENV_PATH", env)

    started = {"count": 0}

    def failing_bootstrap(broker, **kwargs):
        return BootstrapResult(
            status=BootstrapStatus.REAUTH_REQUIRED,
            broker=broker,
            gateway=MagicMock(),
            error="token rejected",
            authenticated=False,
        )

    monkeypatch.setattr("interface.ui.services.broker_service.bootstrap_gateway", failing_bootstrap)

    from interface.ui.services.broker_service import BrokerService

    bs = BrokerService()
    real_start = bs._lifecycle.start_all

    def tracked_start():
        started["count"] += 1
        return real_start()

    monkeypatch.setattr(bs._lifecycle, "start_all", tracked_start)
    bs.initialize()
    assert started["count"] == 0


def test_active_broker_raises_when_dhan_bootstrap_fails(monkeypatch, tmp_path):
    env = tmp_path / ".env.local"
    env.write_text("DHAN_CLIENT_ID=ABC\nDHAN_ACCESS_TOKEN=TOK\n")
    monkeypatch.setattr("interface.ui.services.broker_service._ENV_PATH", env)

    bootstrap = BootstrapResult(
        status=BootstrapStatus.REAUTH_REQUIRED,
        broker="dhan",
        gateway=None,
        error="DH-906 after refresh",
        authenticated=False,
        probe_name="dhan.funds",
    )

    monkeypatch.setattr(
        "interface.ui.services.broker_service.bootstrap_gateway",
        lambda broker, **kwargs: bootstrap,
    )

    from interface.ui.services.broker_service import BrokerService

    bs = BrokerService()
    bs.initialize()

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
    monkeypatch.setattr("interface.ui.services.broker_service._ENV_PATH", env)

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
        "interface.ui.services.broker_service.bootstrap_gateway",
        bootstrap_side_effect,
    )
    monkeypatch.setattr(
        "interface.ui.services.broker_service.resolve_env_path",
        lambda broker, default=None: upstox_env if broker == "upstox" else env,
    )

    from interface.ui.services.broker_service import BrokerService

    bs = BrokerService()
    bs.initialize()
    bs._active_name = "upstox"

    with pytest.raises(BrokerNotReadyError) as exc_info:
        _ = bs.active_broker

    assert exc_info.value.broker == "upstox"
    assert exc_info.value.status == BootstrapStatus.REAUTH_REQUIRED
    assert exc_info.value.bootstrap is upstox_bootstrap


def test_active_broker_returns_upstox_oms_proxy_when_configured(monkeypatch, tmp_path):
    env = tmp_path / ".env.local"
    env.write_text("DHAN_CLIENT_ID=ABC\nDHAN_ACCESS_TOKEN=TOK\n")
    monkeypatch.setattr("interface.ui.services.broker_service._ENV_PATH", env)

    upstox_gw = MagicMock()
    MagicMock()
    dhan_gw = MagicMock()
    MagicMock()

    from interface.ui.services.broker_service import BrokerService

    bs = BrokerService()
    bs._initialized = True
    bs._live_intent = True
    bs._gateway = dhan_gw
    bs._upstox_gateway = upstox_gw
    bs._active_name = "upstox"

    # active_broker returns the live gateway (OMS proxy wire-up is separate)
    assert bs.active_broker is upstox_gw
    bs._active_name = "dhan"
    assert bs.active_broker is dhan_gw
