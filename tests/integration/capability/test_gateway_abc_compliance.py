"""Tests for MarketDataGateway ABC compliance per broker."""

from __future__ import annotations

import inspect

import pytest

from domain.capability_manifest import CAPABILITY_SURFACES, abc_gateway_methods, surface_by_id
from domain.ports.broker_adapter import BrokerAdapter as MarketDataGateway


def _abstract_methods() -> set[str]:
    return {
        name
        for name, fn in inspect.getmembers(MarketDataGateway, predicate=inspect.isfunction)
        if getattr(fn, "__isabstractmethod__", False)
    }


class TestManifestABCEntries:
    """Manifest documents every ABC method with broker refs."""

    @pytest.mark.parametrize("method", sorted(abc_gateway_methods()))
    def test_abc_method_has_surface(self, method: str) -> None:
        surfaces = [s for s in CAPABILITY_SURFACES if s.gateway_method == method]
        assert surfaces, f"No manifest surface for ABC method {method!r}"
        assert any(s.abc_required or s.gateway_method == method for s in surfaces)

    def test_future_chain_upstox_gateway_enabled(self) -> None:
        surface = surface_by_id("derivatives.future_chain")
        assert surface is not None
        assert surface.broker.upstox_known_gap is None
        assert surface.broker.upstox_gateway


class TestGatewayImplementationContract:
    """Gateway classes declare ABC methods (structural check via MRO)."""

    def test_dhan_gateway_implements_abc_methods(self) -> None:
        from brokers.dhan.wire import DhanBrokerGateway as DhanGateway

        abstract = _abstract_methods()
        for method in abstract:
            assert hasattr(DhanGateway, method), f"Dhan DhanBrokerGateway missing {method}"
            impl = getattr(DhanGateway, method)
            assert getattr(impl, "__isabstractmethod__", False) is False

    def test_upstox_gateway_implements_abc_methods(self) -> None:
        from brokers.upstox.wire import UpstoxBrokerGateway

        abstract = _abstract_methods()
        for method in abstract:
            assert hasattr(UpstoxBrokerGateway, method), f"Upstox gateway missing {method}"

    def test_paper_gateway_implements_abc_methods(self) -> None:
        from brokers.paper.paper_gateway import PaperGateway

        abstract = _abstract_methods()
        for method in abstract:
            assert hasattr(PaperGateway, method), f"Paper gateway missing {method}"


class TestUpstoxFutureChain:
    """Upstox future_chain returns FutureChain via futures adapter."""

    def test_upstox_future_chain_returns_chain(self) -> None:
        from brokers.upstox.wire import UpstoxBrokerGateway
        from domain import FutureChain
        from tests.integration.fixtures.upstox import make_mock_broker

        broker = make_mock_broker()
        gw = UpstoxBrokerGateway(broker)
        result = gw.future_chain("NIFTY", "NFO")
        assert isinstance(result, FutureChain)
        assert result.underlying == "NIFTY"
        assert len(result.contracts) >= 1
