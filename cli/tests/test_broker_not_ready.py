"""Tests for BrokerNotReadyError and require_gateway."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from brokers.common.connection.bootstrap_result import BootstrapResult, BootstrapStatus
from brokers.common.connection.errors import BrokerNotReadyError
from cli.services.broker_registry import create_gateway, require_gateway


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


def test_create_gateway_raises_when_configured():
    with patch("cli.services.broker_registry.bootstrap_gateway") as mock_boot:
        mock_boot.return_value = BootstrapResult(
            status=BootstrapStatus.FAILED,
            broker="dhan",
            error="factory failed",
        )
        with pytest.raises(BrokerNotReadyError) as exc_info:
            create_gateway("dhan", raise_on_failure=True)
        assert exc_info.value.broker == "dhan"


def test_require_gateway_delegates_to_create_gateway():
    with patch("cli.services.broker_registry.create_gateway") as mock_create:
        mock_create.return_value = object()
        gw = require_gateway("paper")
        assert gw is mock_create.return_value
        mock_create.assert_called_once()
        assert mock_create.call_args.kwargs["raise_on_failure"] is True
