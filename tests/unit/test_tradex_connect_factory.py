"""Wave D: tradex.connect factory for paper / registry wiring."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

import tradex
from tradex.runtime.adapter_factory import (
    create_execution_provider,
    register_execution_provider,
)
from tradex.runtime.gateway_factory import ENV_FILES, list_available_brokers


def test_list_available_brokers_includes_core():
    names = {b["name"] for b in list_available_brokers()}
    assert {"paper", "dhan", "upstox"}.issubset(names)
    assert ENV_FILES["dhan"] == ".env.local"
    assert ENV_FILES["upstox"] == ".env.upstox"


def test_connect_paper_wires_oms_and_execution():
    session = tradex.connect("paper")
    assert session.order_service is not None
    assert session.execution_provider is not None
    assert session.execution_provider.name == "paper"
    assert session.status is not None
    assert session.status.mode == "sim"
    assert session.status.orders_enabled is True
    assert session.status.phase == "ReadyTrade"
    r = session.buy(session.universe.equity("RELIANCE"), 1, price=Decimal("100"))
    assert r.success is True
    session.close()


def test_connect_unknown_broker_raises():
    from domain.connect_errors import ConnectError

    with pytest.raises(ConnectError) as ei:
        tradex.connect("not-a-broker")
    assert ei.value.code == "UNKNOWN_BROKER"


def test_connect_dhan_market_default_no_oms():
    """TH-1: dhan default mode=market — data path without process OMS."""
    mock_gw = MagicMock(name="DhanGateway")
    mock_gw.place_order.return_value = MagicMock(
        success=True, order_id="DH-1", status="FILLED", message="ok"
    )

    with patch("tradex.runtime.gateway_factory.create_gateway", return_value=mock_gw):
        import brokers.dhan  # noqa: F401

        session = tradex.connect("dhan", load_instruments=False)
        assert session.status is not None
        assert session.status.mode == "market"
        assert session.status.orders_enabled is False
        assert session.status.phase == "ReadyMarket"
        assert session.order_service is None
        assert session.execution_provider is not None
        assert session.execution_provider.name == "dhan"
        # Orders blocked
        with pytest.raises(RuntimeError, match="ORDERS_DISABLED"):
            session.buy(session.universe.equity("RELIANCE"), 1, price=Decimal("100"))
        session.close()


def test_connect_dhan_trade_requires_oms():
    """TH-1: mode=trade without process OMS → ConnectError OMS_REQUIRED."""
    from application.oms.process_context import reset_oms_context
    from domain.connect_errors import ConnectError

    reset_oms_context()
    mock_gw = MagicMock(name="DhanGateway")

    with patch("tradex.runtime.gateway_factory.create_gateway", return_value=mock_gw):
        import brokers.dhan  # noqa: F401

        with pytest.raises(ConnectError) as ei:
            tradex.connect("dhan", mode="trade", load_instruments=False)
        assert ei.value.code == "OMS_REQUIRED"
        assert ei.value.remediation


def test_connect_dhan_trade_with_process_oms():
    """mode=trade reuses registered process OMS context."""
    from application.oms.process_context import register_oms_context, reset_oms_context
    from application.oms.session_bridge import build_oms_service

    reset_oms_context()
    mock_gw = MagicMock(name="DhanGateway")
    mock_ep = MagicMock(name="EP")
    mock_ep.name = "dhan"

    with patch("tradex.runtime.gateway_factory.create_gateway", return_value=mock_gw):
        import brokers.dhan  # noqa: F401
        from application.oms import has_oms_context

        oms_svc = build_oms_service(mock_ep, broker_id="paper")

        class _Ctx:
            order_manager = oms_svc.order_manager

        register_oms_context(_Ctx())  # type: ignore[arg-type]
        assert has_oms_context()
        try:
            session = tradex.connect("dhan", mode="trade", load_instruments=False)
            assert session.status.mode == "trade"
            assert session.status.orders_enabled is True
            assert session.order_service is not None
            session.close()
        finally:
            reset_oms_context()


def test_connect_invalid_mode():
    from domain.connect_errors import ConnectError

    with pytest.raises(ConnectError) as ei:
        tradex.connect("paper", mode="live")
    assert ei.value.code == "UNKNOWN_MODE"


def test_connect_dhan_sim_rejected():
    from domain.connect_errors import ConnectError

    with pytest.raises(ConnectError) as ei:
        tradex.connect("dhan", mode="sim", load_instruments=False)
    assert ei.value.code == "UNKNOWN_MODE"


def test_paper_execution_provider_registered():
    import brokers.paper  # noqa: F401

    gw = MagicMock()
    ep = create_execution_provider(gw, broker_id="paper")
    assert ep is not None
    assert ep.name == "paper"


def test_cli_broker_registry_reexports_create_gateway():
    from cli.services.broker_registry import create_gateway as cli_cg
    from tradex.runtime.gateway_factory import create_gateway as runtime_cg

    assert cli_cg is runtime_cg
