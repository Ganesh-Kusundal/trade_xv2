"""Upstox future_chain gateway behavior (capability contract)."""

from __future__ import annotations


class TestUpstoxFutureChain:
    """Upstox future_chain returns FutureChain via futures adapter."""

    def test_upstox_future_chain_returns_chain(self) -> None:
        from brokers.providers.upstox.wire import UpstoxWireAdapter
        from domain import FutureChain
        from tests.integration.fixtures.upstox import make_mock_broker

        broker = make_mock_broker()
        gw = UpstoxWireAdapter(broker)
        result = gw.future_chain("NIFTY", "NFO")
        assert isinstance(result, FutureChain)
        assert result.underlying == "NIFTY"
        assert len(result.contracts) >= 1
