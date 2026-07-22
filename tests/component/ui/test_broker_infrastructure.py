"""BrokerService integration with broker gateways."""

from __future__ import annotations

import pytest

from interface.ui.services.broker_service import BrokerService


@pytest.fixture(autouse=True)
def _block_live_env_bootstrap(monkeypatch, tmp_path):
    """Avoid live Dhan bootstrap when .env.local exists on developer machines."""
    monkeypatch.setenv("TRADEX_ENV_FILE", str(tmp_path / "missing.env.local"))
    monkeypatch.setenv("TRADEX_UPSTOX_ENV_FILE", str(tmp_path / "missing.env.upstox"))
    monkeypatch.setattr(
        "interface.ui.services.broker_registry.resolve_env_path",
        lambda _broker_id: None,
    )


def test_broker_service_builds_infrastructure_with_paper():
    service = BrokerService()
    service.set_active_broker("paper")
    # Verify the paper broker is available through the current API
    assert service.active_broker_name == "paper"
    assert "paper" in service.gateways or service.active_broker is not None
    service.close()
