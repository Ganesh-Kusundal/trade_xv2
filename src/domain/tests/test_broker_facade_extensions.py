"""Instrument.broker extensions stamped at connect (no gateway in product path)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import tradex
from domain.extensions.facade import BoundBrokerFacade, BrokerFacade


class _FakeDepth20:
    name = "depth_20"
    broker = "dhan"
    capabilities = ()

    def __init__(self, gateway=None) -> None:
        self._gw = gateway
        self._symbol = ""
        self._exchange = "NSE"
        self.calls: list[tuple] = []

    def for_instrument(self, symbol: str, exchange: str = "NSE") -> "_FakeDepth20":
        e = type(self)(self._gw)
        e._symbol = symbol
        e._exchange = exchange
        e.calls = self.calls
        return e

    def full_depth(self, on_depth=None):
        self.calls.append((self._symbol, self._exchange, on_depth))
        return {"levels": 20, "symbol": self._symbol}


class _FakeDepth200(_FakeDepth20):
    name = "depth_200"

    def full_depth(self, on_depth=None):
        self.calls.append((self._symbol, self._exchange, on_depth))
        return {"levels": 200, "symbol": self._symbol}


def test_bound_facade_depth20_uses_instrument_symbol():
    catalog = BrokerFacade("dhan", [_FakeDepth20()])
    inst = MagicMock()
    inst.symbol = "RELIANCE"
    inst.exchange = "NSE"
    bound = catalog.for_instrument(inst)
    assert isinstance(bound, BoundBrokerFacade)
    assert "depth_20" in bound.capabilities
    out = bound.depth20()
    assert out["levels"] == 20
    assert out["symbol"] == "RELIANCE"


def test_connect_dhan_stamps_extensions_on_instrument():
    from domain.ports.bootstrap import BootstrapResult, BootstrapStatus

    mock_gw = MagicMock(name="DhanGateway")
    mock_gw.extension_registry = None
    mock_gw.get_extension = MagicMock(side_effect=Exception("none"))

    ready = BootstrapResult(
        status=BootstrapStatus.READY,
        broker="dhan",
        gateway=mock_gw,
        authenticated=True,
        probe_passed=True,
        probe_name="mock",
    )
    with (
        patch("infrastructure.gateway.factory.bootstrap_gateway", return_value=ready),
        patch(
            "infrastructure.adapter_factory.get_broker_extension_classes",
            return_value=[_FakeDepth20, _FakeDepth200],
        ),
    ):
        import brokers.dhan  # noqa: F401

        session = tradex.connect("dhan", mode="market", load_instruments=False)
        eq = session.universe.equity("RELIANCE")
        assert eq.broker is not None
        assert isinstance(eq.broker, BoundBrokerFacade)
        caps = eq.capabilities()
        assert "depth_20" in caps or "depth_200" in caps
        d = eq.broker.depth20()
        assert d["symbol"] == "RELIANCE"
        d2 = eq.broker.depth200()
        assert d2["levels"] == 200
        # get_extension binds
        ext = eq.get_extension("depth_20")
        assert ext is not None
        assert getattr(ext, "_symbol", None) == "RELIANCE"
        session.close()


def test_paper_broker_facade_empty_capabilities():
    session = tradex.connect("paper")
    eq = session.universe.equity("RELIANCE")
    # empty catalog still returns bound facade with no depth
    assert eq.broker is not None
    with pytest.raises(AttributeError, match="depth"):
        eq.broker.depth20()
    session.close()
