"""Cross-broker BrokerTransport contract — the shared spec every plugin must pass.

Subclass ``_BrokerTransportContract`` (prefix ``_`` so pytest does not collect
the base) and implement ``build_transport`` with a concrete broker transport.
The inherited tests then prove the transport conforms to the domain's broker
port across all six surfaces (market / orders / portfolio / historical /
streaming / capabilities) — the enforceable parity the roadmap requires.
"""

from __future__ import annotations

from decimal import Decimal

from domain.capabilities import Capability
from domain.instruments.instrument_id import InstrumentId
from domain.orders.requests import OrderRequest
from domain.ports.broker_transport import BrokerTransport
from domain.ports.protocols import DataProvider, ExecutionProvider, OrderResult
from domain.tests._fakes import FakeProvider
from domain.types import OrderType, ProductType, Side


class FakeExecutionProvider:
    """In-memory ExecutionProvider for the contract test."""

    def __init__(self) -> None:
        self.name = "fake"
        self.placed: list[OrderRequest] = []

    def place_order(self, request: OrderRequest) -> OrderResult:
        self.placed.append(request)
        return OrderResult.ok("O1")

    def cancel_order(self, order_id: str) -> OrderResult:
        return OrderResult.ok("O1")

    def modify_order(self, request) -> OrderResult:
        return OrderResult.ok("O1")

    def get_order_book(self):
        return []

    def get_positions(self):
        return []

    def get_holdings(self):
        return []

    def get_funds(self):
        return None


class FakeTransport(BrokerTransport):
    """Reference transport backed by in-memory fakes."""

    def __init__(self) -> None:
        self._market = FakeProvider()
        self._market.seed_quote("RELIANCE", "NSE", Decimal("2500"))
        self._exec = FakeExecutionProvider()

    @property
    def name(self) -> str:
        return "fake"

    @property
    def market_data(self) -> DataProvider:
        return self._market

    @property
    def execution(self) -> ExecutionProvider:
        return self._exec

    def capabilities(self) -> list[Capability]:
        return [Capability.MARKET_DATA, Capability.ORDER_COMMAND, Capability.OPTIONS_CHAIN]

    def close(self) -> None:
        pass


class _BrokerTransportContract:
    """Shared BrokerTransport conformance contract (not collected directly)."""

    def build_transport(self) -> BrokerTransport:
        raise NotImplementedError

    def test_name_present(self) -> None:
        assert self.build_transport().name

    def test_market_data_is_data_provider(self) -> None:
        t = self.build_transport()
        assert isinstance(t.market_data, DataProvider)
        quote = t.market_data.get_quote(InstrumentId.equity("NSE", "RELIANCE"))
        assert quote is not None

    def test_execution_is_execution_provider(self) -> None:
        t = self.build_transport()
        assert isinstance(t.execution, ExecutionProvider)

    def test_capabilities_are_domain_enum(self) -> None:
        caps = self.build_transport().capabilities()
        assert isinstance(caps, list)
        assert all(isinstance(c, Capability) for c in caps)

    def test_supports_discovery(self) -> None:
        t = self.build_transport()
        caps = t.capabilities()
        if caps:
            assert t.supports(caps[0]) is True
        assert t.supports(Capability.GLOBAL_MARKETS) is False

    def test_execution_roundtrip(self) -> None:
        t = self.build_transport()
        req = OrderRequest(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type=Side.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
        )
        res = t.execution.place_order(req)
        assert res.success is True


class TestFakeTransportContract(_BrokerTransportContract):
    def build_transport(self) -> BrokerTransport:
        return FakeTransport()
