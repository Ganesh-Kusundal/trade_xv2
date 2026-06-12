"""Pytest fixtures for Dhan integration tests."""

from __future__ import annotations

import pytest

from brokers.common.core.connection import ConnectionStatus
from brokers.dhan.tests.integration.dhan_safety import (
    install_live_mutation_guard,
    make_broker,
    require_integration_enabled,
    resolve_env_path,
)


@pytest.fixture
def sandbox_broker(monkeypatch: pytest.MonkeyPatch) -> object:
    require_integration_enabled()
    env_path = resolve_env_path("sandbox")
    broker = make_broker(env_path)

    if not broker.settings.is_sandbox:
        pytest.skip("DHAN_ENVIRONMENT must be SANDBOX for sandbox OMS tests")

    assert broker.connect()
    assert broker.status == ConnectionStatus.CONNECTED

    try:
        yield broker
    finally:
        broker.disconnect()


@pytest.fixture
def live_readonly_broker(monkeypatch: pytest.MonkeyPatch) -> object:
    require_integration_enabled()
    env_path = resolve_env_path("live_readonly")
    broker = make_broker(env_path)

    if broker.settings.is_sandbox:
        pytest.skip("DHAN_ENVIRONMENT must be LIVE for live read-only tests")

    install_live_mutation_guard(monkeypatch, broker)

    assert broker.connect()
    assert broker.status == ConnectionStatus.CONNECTED

    try:
        yield broker
    finally:
        broker.disconnect()
