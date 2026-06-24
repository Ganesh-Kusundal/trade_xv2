"""BrokerService fail-closed behavior for authenticated readiness."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brokers.common.connection.bootstrap_result import BootstrapResult, BootstrapStatus


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
    monkeypatch.setattr("cli.services.broker_service.start_http_observability", lambda *a, **k: None)
    monkeypatch.setattr("cli.services.broker_service.start_websocket_services", lambda *a, **k: None)

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
    original_start = None

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
