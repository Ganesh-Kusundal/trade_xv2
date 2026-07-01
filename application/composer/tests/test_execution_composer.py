"""Tests for ExecutionComposer kill-switch enforcement."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from application.composer.execution import ExecutionComposer


class TestExecutionComposerKillSwitch:
    """Test kill-switch guard in ExecutionComposer."""

    @pytest.fixture
    def mock_registry(self) -> MagicMock:
        """Create a mock BrokerRegistry."""
        registry = MagicMock()
        gateway = AsyncMock()
        gateway.place_order.return_value = MagicMock(
            success=True, order_id="test-order-123", status="OPEN"
        )
        registry.get_gateway.return_value = gateway
        return registry

    @pytest.fixture
    def mock_router(self) -> MagicMock:
        """Create a mock BrokerRouter."""
        router = MagicMock()
        decision = MagicMock()
        decision.primary_broker = "dhan"
        router.route.return_value = decision
        return router

    @pytest.fixture
    def mock_quota_scheduler(self) -> AsyncMock:
        """Create a mock QuotaScheduler."""
        scheduler = AsyncMock()
        scheduler.acquire_async.return_value = MagicMock()
        return scheduler

    @pytest.fixture
    def composer(
        self,
        mock_registry: MagicMock,
        mock_router: MagicMock,
        mock_quota_scheduler: AsyncMock,
    ) -> ExecutionComposer:
        """Create ExecutionComposer without risk_manager."""
        return ExecutionComposer(
            registry=mock_registry,
            router=mock_router,
            quota_scheduler=mock_quota_scheduler,
        )

    @pytest.fixture
    def composer_with_risk(
        self,
        mock_registry: MagicMock,
        mock_router: MagicMock,
        mock_quota_scheduler: AsyncMock,
    ) -> ExecutionComposer:
        """Create ExecutionComposer with risk_manager."""
        risk_manager = MagicMock()
        risk_manager.is_kill_switch_active.return_value = False
        return ExecutionComposer(
            registry=mock_registry,
            router=mock_router,
            quota_scheduler=mock_quota_scheduler,
            risk_manager=risk_manager,
        )

    @pytest.mark.asyncio
    async def test_place_order_without_risk_manager_succeeds(
        self, composer: ExecutionComposer
    ) -> None:
        """Test that place_order works when risk_manager is None."""
        request = MagicMock()
        request.symbol = "RELAYANCE"
        request.side = "BUY"
        request.quantity = 10

        result = await composer.place_order(request)

        assert result.success is True
        assert result.order_id == "test-order-123"

    @pytest.mark.asyncio
    async def test_place_order_with_kill_switch_inactive_succeeds(
        self, composer_with_risk: ExecutionComposer
    ) -> None:
        """Test that place_order works when kill switch is inactive."""
        request = MagicMock()
        request.symbol = "RELIANCE"
        request.side = "BUY"
        request.quantity = 10

        result = await composer_with_risk.place_order(request)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_place_order_with_kill_switch_active_raises(
        self,
        mock_registry: MagicMock,
        mock_router: MagicMock,
        mock_quota_scheduler: AsyncMock,
    ) -> None:
        """Test that place_order raises OrderBlockedError when kill switch is active."""
        from application.oms.oms_gateway_proxy import OrderBlockedError

        risk_manager = MagicMock()
        risk_manager.is_kill_switch_active.return_value = True

        composer = ExecutionComposer(
            registry=mock_registry,
            router=mock_router,
            quota_scheduler=mock_quota_scheduler,
            risk_manager=risk_manager,
        )

        request = MagicMock()
        request.symbol = "RELIANCE"
        request.side = "BUY"
        request.quantity = 10

        with pytest.raises(OrderBlockedError) as exc_info:
            await composer.place_order(request)

        assert "kill switch active" in str(exc_info.value).lower()
        assert exc_info.value.operation == "place_order"

    @pytest.mark.asyncio
    async def test_cancel_order_with_kill_switch_active_raises(
        self,
        mock_registry: MagicMock,
        mock_router: MagicMock,
        mock_quota_scheduler: AsyncMock,
    ) -> None:
        """Test that cancel_order raises OrderBlockedError when kill switch is active."""
        from application.oms.oms_gateway_proxy import OrderBlockedError

        risk_manager = MagicMock()
        risk_manager.is_kill_switch_active.return_value = True

        composer = ExecutionComposer(
            registry=mock_registry,
            router=mock_router,
            quota_scheduler=mock_quota_scheduler,
            risk_manager=risk_manager,
        )

        with pytest.raises(OrderBlockedError) as exc_info:
            await composer.cancel_order("order-123")

        assert exc_info.value.operation == "cancel_order"

    @pytest.mark.asyncio
    async def test_modify_order_with_kill_switch_active_raises(
        self,
        mock_registry: MagicMock,
        mock_router: MagicMock,
        mock_quota_scheduler: AsyncMock,
    ) -> None:
        """Test that modify_order raises OrderBlockedError when kill switch is active."""
        from application.oms.oms_gateway_proxy import OrderBlockedError

        risk_manager = MagicMock()
        risk_manager.is_kill_switch_active.return_value = True

        composer = ExecutionComposer(
            registry=mock_registry,
            router=mock_router,
            quota_scheduler=mock_quota_scheduler,
            risk_manager=risk_manager,
        )

        request = MagicMock()
        request.order_id = "order-123"

        with pytest.raises(OrderBlockedError) as exc_info:
            await composer.modify_order(request)

        assert exc_info.value.operation == "modify_order"

    @pytest.mark.asyncio
    async def test_check_kill_switch_is_noop_without_risk_manager(
        self, composer: ExecutionComposer
    ) -> None:
        """Test that _check_kill_switch is a no-op when risk_manager is None."""
        # Should not raise
        composer._check_kill_switch("test_operation")

    def test_check_kill_switch_raises_when_active(
        self,
        mock_registry: MagicMock,
        mock_router: MagicMock,
        mock_quota_scheduler: AsyncMock,
    ) -> None:
        """Test that _check_kill_switch raises when kill switch is active."""
        from application.oms.oms_gateway_proxy import OrderBlockedError

        risk_manager = MagicMock()
        risk_manager.is_kill_switch_active.return_value = True

        composer = ExecutionComposer(
            registry=mock_registry,
            router=mock_router,
            quota_scheduler=mock_quota_scheduler,
            risk_manager=risk_manager,
        )

        with pytest.raises(OrderBlockedError):
            composer._check_kill_switch("test_operation")
