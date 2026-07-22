"""Unit tests for Unified ExecutionEngine order routing across execution modes."""

from decimal import Decimal
import pytest
from application.execution.execution_engine import ExecutionEngine
from domain.enums import OrderType, Side, ProductType, Validity
from domain.orders.requests import OrderRequest


@pytest.mark.asyncio
async def test_execution_engine_routes_order_to_gateway():
    processed_requests = []

    class MockGateway:
        def place_order(self, request: OrderRequest):
            processed_requests.append(request)
            return type("Resp", (), {"order_id": "GW-999", "status": "OPEN"})()

    engine = ExecutionEngine(gateway=MockGateway())
    
    order_id = await engine.submit_order(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=25,
        price=Decimal("2500.00"),
        order_type=OrderType.LIMIT,
    )

    assert order_id == "GW-999"
    assert len(processed_requests) == 1
    assert processed_requests[0].symbol == "RELIANCE"
    assert processed_requests[0].quantity == 25
