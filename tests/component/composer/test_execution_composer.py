"""Tests for ExecutionComposer kill-switch enforcement via OMS (not composer pre-check)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from application.composer.execution import ExecutionComposer
from application.oms.order_manager import OrderResult
from domain.orders.requests import OrderRequest
from domain.enums import OrderType, ProductType, Side
from domain.ports.execution_target import ExecutionTargetKind


@pytest.fixture(autouse=True)
def _wire_runtime_async_bridge():
    from runtime.composition import wire_domain_port_sinks

    wire_domain_port_sinks()


class TestExecutionComposerKillSwitch:
    """Kill-switch is enforced by OrderManager/OrderLifecycle, not composer."""

    @pytest.fixture
    def mock_registry(self) -> MagicMock:
        registry = MagicMock()
        gateway = AsyncMock()
        gateway.place_order.return_value = MagicMock(
            success=True, order_id="test-order-123", status="OPEN"
        )
        registry.get_gateway.return_value = gateway
        return registry

    @pytest.fixture
    def mock_router(self) -> MagicMock:
        router = MagicMock()
        decision = MagicMock()
        decision.primary_broker = "dhan"
        router.route.return_value = decision
        return router

    @pytest.fixture
    def mock_quota_scheduler(self) -> AsyncMock:
        scheduler = AsyncMock()
        scheduler.acquire_async.return_value = MagicMock()
        return scheduler

    @pytest.fixture
    def mock_risk_manager(self) -> MagicMock:
        risk_manager = MagicMock()
        risk_manager.is_kill_switch_active.return_value = False
        return risk_manager

    @pytest.fixture
    def mock_order_manager(self) -> MagicMock:
        from domain.entities import Order
        from domain.types import OrderStatus, OrderType, ProductType, Side

        om = MagicMock()
        om.place_order.return_value = OrderResult(
            success=True,
            order=Order(
                order_id="test-order-123",
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                order_type=OrderType.MARKET,
                quantity=10,
                product_type=ProductType.INTRADAY,
                status=OrderStatus.OPEN,
            ),
        )
        om.cancel_order.return_value = OrderResult(success=True)
        om.modify_order.return_value = OrderResult(success=True)
        return om

    @pytest.fixture
    def composer(
        self,
        mock_registry: MagicMock,
        mock_router: MagicMock,
        mock_quota_scheduler: AsyncMock,
        mock_risk_manager: MagicMock,
        mock_order_manager: MagicMock,
    ) -> ExecutionComposer:
        return ExecutionComposer(
            registry=mock_registry,
            router=mock_router,
            quota_scheduler=mock_quota_scheduler,
            risk_manager=mock_risk_manager,
            order_manager=mock_order_manager,
            execution_target_kind=ExecutionTargetKind.PAPER,
        )

    @pytest.mark.asyncio
    async def test_place_order_delegates_to_oms(self, composer: ExecutionComposer) -> None:
        request = OrderRequest(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type=Side.BUY,
            quantity=10,
            price=Decimal("0"),
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
            correlation_id="composer:test:place",
        )

        result = await composer.place_order(request)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_cancel_order_oms_rejection_surfaces_as_failure(
        self,
        mock_registry: MagicMock,
        mock_router: MagicMock,
        mock_quota_scheduler: AsyncMock,
        mock_risk_manager: MagicMock,
    ) -> None:
        om = MagicMock()
        om.cancel_order.return_value = OrderResult(
            success=False,
            error="Order blocked: kill switch active (cancel)",
        )
        composer = ExecutionComposer(
            registry=mock_registry,
            router=mock_router,
            quota_scheduler=mock_quota_scheduler,
            risk_manager=mock_risk_manager,
            order_manager=om,
            execution_target_kind=ExecutionTargetKind.PAPER,
        )

        result = await composer.cancel_order("order-123")

        assert not result.success
        assert "kill switch" in (result.message or "").lower()

    @pytest.mark.asyncio
    async def test_modify_order_oms_rejection_surfaces_as_failure(
        self,
        mock_registry: MagicMock,
        mock_router: MagicMock,
        mock_quota_scheduler: AsyncMock,
        mock_risk_manager: MagicMock,
    ) -> None:
        om = MagicMock()
        om.modify_order.return_value = OrderResult(
            success=False,
            error="Order blocked: kill switch active (modify)",
        )
        composer = ExecutionComposer(
            registry=mock_registry,
            router=mock_router,
            quota_scheduler=mock_quota_scheduler,
            risk_manager=mock_risk_manager,
            order_manager=om,
            execution_target_kind=ExecutionTargetKind.PAPER,
        )
        request = MagicMock()
        request.order_id = "order-123"

        result = await composer.modify_order(request)

        assert not result.success
        assert "kill switch" in (result.message or "").lower()
