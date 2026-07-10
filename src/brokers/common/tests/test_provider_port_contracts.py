"""Port contracts: DataProvider / ExecutionProvider (Wave C).

Instrument + OMS use these ports. Gateway suites remain for transport facades.
Offline fakes cover paper, DhanOrderTransport, and UpstoxExecutionProvider
without live credentials.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from brokers.dhan.api.transport import DhanOrderTransport
from brokers.paper.data_provider import PaperDataProvider
from brokers.paper.execution_provider import PaperExecutionProvider
from brokers.paper.paper_gateway import PaperGateway
from brokers.upstox import UpstoxExecutionProvider
from domain.entities.order import OrderResponse
from domain.instruments.instrument_id import InstrumentId
from domain.orders.requests import OrderRequest
from domain.ports.protocols import DataProvider, ExecutionProvider, OrderResult
from domain.types import OrderType, ProductType, Side, Validity


def _order_request(correlation_id: str) -> OrderRequest:
    return OrderRequest(
        symbol="RELIANCE",
        exchange="NSE",
        transaction_type=Side.BUY,
        quantity=1,
        price=Decimal("100"),
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        validity=Validity.DAY,
        correlation_id=correlation_id,
    )


class _FakeGateway:
    """Minimal duck-typed gateway for offline ExecutionProvider contracts."""

    def __init__(self) -> None:
        self.orders: list[dict[str, Any]] = []
        self._n = 0

    def place_order(self, **kwargs: Any) -> OrderResponse:
        self._n += 1
        oid = f"FAKE-{self._n}"
        self.orders.append({"order_id": oid, **kwargs})
        return OrderResponse.ok(order_id=oid, message="placed")

    def cancel_order(self, order_id: str) -> OrderResponse:
        return OrderResponse.ok(order_id=order_id, message="cancelled")

    def modify_order(self, order_id: str, **kwargs: Any) -> OrderResponse:
        return OrderResponse.ok(order_id=order_id, message="modified")

    def get_orderbook(self) -> list:
        return []

    def positions(self) -> list:
        return []

    def holdings(self) -> list:
        return []

    def funds(self) -> Any:
        return SimpleNamespace(available_balance=Decimal("100000"))

    def quote(self, symbol: str, exchange: str = "NSE") -> Any:
        return SimpleNamespace(ltp=Decimal("2500"), bid=Decimal("2499"), ask=Decimal("2501"), volume=0)

    def close(self) -> None:
        pass


@pytest.fixture
def paper_gw():
    return PaperGateway()


@pytest.fixture
def paper_data(paper_gw) -> DataProvider:
    return PaperDataProvider(paper_gw)


@pytest.fixture
def paper_execution(paper_gw) -> ExecutionProvider:
    return PaperExecutionProvider(paper_gw)


@pytest.fixture
def dhan_execution() -> ExecutionProvider:
    return DhanOrderTransport(_FakeGateway())


@pytest.fixture
def upstox_execution() -> ExecutionProvider:
    return UpstoxExecutionProvider(_FakeGateway())


# ── Paper DataProvider ────────────────────────────────────────────────────


def test_paper_data_provider_runtime_checkable(paper_data):
    assert isinstance(paper_data, DataProvider)


def test_paper_data_provider_name(paper_data):
    assert paper_data.name == "paper"


def test_paper_get_quote_or_none(paper_data):
    iid = InstrumentId.equity("NSE", "RELIANCE")
    q = paper_data.get_quote(iid)
    assert q is None or getattr(q, "ltp", None) is not None


# ── ExecutionProvider matrix (paper + offline broker transports) ──────────


@pytest.mark.parametrize(
    "fixture_name,expected_name",
    [
        ("paper_execution", "paper"),
        ("dhan_execution", "dhan"),
        ("upstox_execution", "upstox"),
    ],
)
def test_execution_provider_runtime_checkable(request, fixture_name, expected_name):
    execution: ExecutionProvider = request.getfixturevalue(fixture_name)
    assert isinstance(execution, ExecutionProvider)
    assert execution.name == expected_name


@pytest.mark.parametrize(
    "fixture_name",
    ["paper_execution", "dhan_execution", "upstox_execution"],
)
def test_place_order_returns_order_result(request, fixture_name):
    execution: ExecutionProvider = request.getfixturevalue(fixture_name)
    result = execution.place_order(_order_request(f"port-contract:{fixture_name}"))
    assert isinstance(result, OrderResult)
    assert result.success is True
    assert result.order is not None


@pytest.mark.parametrize(
    "fixture_name,expect_success",
    [
        # Paper fills LIMIT instantly → cancel may fail (already filled) — still OrderResult
        ("paper_execution", None),
        ("dhan_execution", True),
        ("upstox_execution", True),
    ],
)
def test_cancel_order_returns_order_result(request, fixture_name, expect_success):
    execution: ExecutionProvider = request.getfixturevalue(fixture_name)
    placed = execution.place_order(_order_request(f"port-contract:cancel:{fixture_name}"))
    order_id = getattr(placed.order, "order_id", None) or "unknown"
    result = execution.cancel_order(str(order_id))
    assert isinstance(result, OrderResult)
    if expect_success is True:
        assert result.success is True


def test_dhan_transport_failure_is_order_result_fail():
    gw = MagicMock()
    gw.place_order.side_effect = RuntimeError("network down")
    execution = DhanOrderTransport(gw)
    result = execution.place_order(_order_request("port-contract:fail"))
    assert result.success is False
    assert "network" in (result.error or "").lower() or "down" in (result.error or "").lower()


@pytest.mark.parametrize(
    "fixture_name",
    ["paper_execution", "dhan_execution", "upstox_execution"],
)
def test_portfolio_queries_return_lists(request, fixture_name):
    """ExecutionProvider portfolio reads stay list-typed (Wave C)."""
    execution: ExecutionProvider = request.getfixturevalue(fixture_name)
    assert isinstance(execution.get_order_book(), list)
    assert isinstance(execution.get_positions(), list)
    assert isinstance(execution.get_holdings(), list)
