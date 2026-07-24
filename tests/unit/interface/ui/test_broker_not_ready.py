"""Tests for BrokerNotReadyError and require_gateway."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from domain.exceptions import BrokerNotReadyError
from infrastructure.connection.bootstrap_result import BootstrapResult, BootstrapStatus
from interface.ui.services.broker_registry import require_gateway


def test_broker_not_ready_from_bootstrap():
    result = BootstrapResult(
        status=BootstrapStatus.REAUTH_REQUIRED,
        broker="dhan",
        error="token rejected",
    )
    err = BrokerNotReadyError.from_bootstrap(result)
    assert err.broker == "dhan"
    assert err.status == BootstrapStatus.REAUTH_REQUIRED
    assert "token rejected" in str(err)


def test_require_gateway_raises_when_bootstrap_fails():
    with patch("infrastructure.gateway.factory.bootstrap_gateway") as mock_boot:
        mock_boot.return_value = BootstrapResult(
            status=BootstrapStatus.FAILED,
            broker="dhan",
            error="factory failed",
        )
        with pytest.raises(BrokerNotReadyError) as exc_info:
            require_gateway("dhan")
        assert exc_info.value.broker == "dhan"


def test_require_gateway_returns_gateway_when_ready():
    gw = object()
    with patch("infrastructure.gateway.factory.bootstrap_gateway") as mock_boot:
        mock_boot.return_value = BootstrapResult(
            status=BootstrapStatus.READY,
            broker="paper",
            gateway=gw,
            authenticated=True,
            probe_passed=True,
        )
        assert require_gateway("paper") is gw
