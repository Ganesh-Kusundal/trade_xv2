"""TRANS-P5-021 — tradex.open_session delegates trade mode to runtime.factory.build."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from domain.session_status import MODE_TRADE
from tradex.session import open_session


@pytest.mark.unit
def test_trade_mode_uses_runtime_factory_when_broker_service_provided() -> None:
    mock_oms = MagicMock()
    mock_oms.order_manager = MagicMock()
    mock_runtime = MagicMock()
    mock_runtime.oms_service = mock_oms
    mock_runtime.event_bus = MagicMock()
    mock_runtime.gateway = MagicMock()

    mock_bs = MagicMock()
    mock_bs._active_name = "dhan"

    with patch("runtime.factory.build", return_value=mock_runtime) as build_fn:
        session = open_session(
            "dhan",
            mode=MODE_TRADE,
            broker_service=mock_bs,
            gateway=MagicMock(),
            execution_provider=MagicMock(),
            load_instruments=False,
        )

    build_fn.assert_called_once()
    call_kwargs = build_fn.call_args
    assert call_kwargs[0][0] is mock_bs
    assert call_kwargs[1]["mode"] == "trade"
    assert session._order_service is mock_oms
