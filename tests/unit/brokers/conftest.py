"""Shared fixtures for the broker unit test suite."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def _wire_session_historical_for_broker_tests() -> None:
    from runtime.session_historical import wire_session_historical

    wire_session_historical()


@pytest.fixture(scope="session", autouse=True)
def _wire_async_runner_for_broker_tests() -> None:
    """async_compat sync path requires composition-root wiring."""
    from runtime.composition import wire_domain_port_sinks

    wire_domain_port_sinks()
