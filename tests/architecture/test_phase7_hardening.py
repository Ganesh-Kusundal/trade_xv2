"""Phase 7 hardening checks — architecture invariants for the public SDK."""

from __future__ import annotations

import importlib
from pathlib import Path


def test_broker_gateways_importable() -> None:
    import brokers.dhan.gateway  # noqa: F401
    import brokers.upstox.gateway  # noqa: F401


def test_single_instrument_state_export() -> None:
    from domain.instruments import instrument as inst_mod
    from domain.value_objects.state import InstrumentState

    assert not hasattr(inst_mod, "InstrumentState") or inst_mod.InstrumentState is InstrumentState
    # Local class removed — Instrument imports VO
    assert "from domain.value_objects.state import" in Path(inst_mod.__file__).read_text()


def test_oms_gateway_proxy_removed() -> None:
    import application.oms as oms

    assert not hasattr(oms, "OMSGatewayProxy")
    assert hasattr(oms, "OrderBlockedError")
    assert not Path("application/oms/oms_gateway_proxy.py").exists()


def test_tradex_session_paper_smoke() -> None:
    import tradex

    session = tradex.Session(broker="paper")
    eq = session.universe.equity("INFY")
    assert eq.symbol == "INFY"
    assert eq.refresh() is not None
    session.close()


def test_order_ack_strips_transport() -> None:
    from domain.entities.order import OrderAck, OrderResponse

    resp = OrderResponse.ok("OID-1", raw_payload={"x": 1}, http_status=200)
    ack = resp.to_ack()
    assert isinstance(ack, OrderAck)
    assert not hasattr(ack, "raw_payload")
    assert not hasattr(ack, "http_status")


def test_broker_contract_module_loads() -> None:
    mod = importlib.import_module("brokers.common.contracts.broker_contract")
    assert mod is not None
