"""Tests for service container initialization and dependency injection.

Verifies that:
- Container cannot be modified after set_container is called (idempotent guard)
- All DI dependencies work correctly
- Error messages are actionable when services not available
- Idempotent initialization (calling twice doesn't crash)
- OMS readiness check works correctly
"""

from __future__ import annotations
from tests.conftest import build_test_trading_context

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from interface.api.deps import (
    get_broker_service,
    get_container,
    get_data_catalog,
    get_datalake_gateway,
    get_event_bus,
    get_order_manager,
    get_position_manager,
    get_risk_manager,
    get_trading_context,
    get_view_manager,
    initialize_all_services,
    set_container,
)
from application.oms.context import TradingContext
from infrastructure.event_bus import EventBus


class TestServiceContainerInitialization:
    """Test container initialization behavior."""

    def setup_method(self):
        """Reset container before each test."""
        import interface.api.deps as deps

        deps._container = None
        from infrastructure.di import container as di

        di.reset()

    def teardown_method(self):
        """Clean up container after each test."""
        import interface.api.deps as deps

        deps._container = None
        from infrastructure.di import container as di

        di.reset()

    def test_set_container_initializes_container(self):
        """set_container should set the global container."""
        ns = SimpleNamespace(datalake_gateway="test_gateway")
        set_container(ns)

        container = get_container()
        assert container.datalake_gateway == "test_gateway"

    def test_set_container_is_idempotent(self, caplog):
        """Calling set_container twice should not overwrite (idempotent)."""
        ns1 = SimpleNamespace(datalake_gateway="first")
        ns2 = SimpleNamespace(datalake_gateway="second")

        set_container(ns1)
        with caplog.at_level("WARNING"):
            set_container(ns2)

        # Should still have ns1
        assert get_container().datalake_gateway == "first"
        assert "already initialized" in caplog.text

    def test_initialize_all_services_creates_container(self):
        """initialize_all_services should create and set the container."""
        event_bus = EventBus()

        initialize_all_services(
            datalake_gateway="gateway",
            event_bus=event_bus,
        )

        container = get_container()
        assert container.datalake_gateway == "gateway"
        assert container.event_bus is event_bus

    def test_initialize_all_services_extracts_oms_components(self):
        """OMS components should be extracted from TradingContext."""
        event_bus = EventBus()
        ctx = build_test_trading_context(event_bus=event_bus)

        initialize_all_services(
            event_bus=event_bus,
            trading_context=ctx,
        )

        container = get_container()
        assert container.trading_context is ctx
        assert container.order_manager is ctx.order_manager
        assert container.position_manager is ctx.position_manager
        assert container.risk_manager is ctx.risk_manager

    def test_initialize_all_services_logs_missing_services(self, caplog):
        """Should log warning when services are missing."""
        with caplog.at_level("WARNING"):
            initialize_all_services()  # No services provided

        assert "missing" in caplog.text.lower() or "Services initialized" in caplog.text


class TestDIContainerIntegration:
    """Test that services are stored in the DI container (single source of truth)."""

    def setup_method(self):
        """Reset container before each test."""
        import interface.api.deps as deps

        deps._container = None
        from infrastructure.di import container as di

        di.reset()

    def teardown_method(self):
        """Clean up container after each test."""
        import interface.api.deps as deps

        deps._container = None
        from infrastructure.di import container as di

        di.reset()

    def test_services_registered_in_di_container(self):
        """Services should be accessible via di_container.resolve()."""
        from infrastructure.di import container as di

        event_bus = EventBus()
        mock_gateway = MagicMock()
        initialize_all_services(
            datalake_gateway=mock_gateway,
            event_bus=event_bus,
        )

        assert di.resolve("datalake_gateway") is mock_gateway
        assert di.resolve("event_bus") is event_bus

    def test_di_container_has_all_registered_services(self):
        """di_container.has() should return True for registered services."""
        from infrastructure.di import container as di

        event_bus = EventBus()
        initialize_all_services(event_bus=event_bus)

        assert di.has("event_bus")
        assert di.has("datalake_gateway")

    def test_get_container_returns_simple_namespace(self):
        """get_container should return a SimpleNamespace with service attributes."""
        ns = SimpleNamespace(datalake_gateway="gw", event_bus="eb")
        set_container(ns)

        result = get_container()
        assert isinstance(result, SimpleNamespace)
        assert result.datalake_gateway == "gw"
        assert result.event_bus == "eb"


class TestDIDependencies:
    """Test FastAPI dependency injection functions."""

    def setup_method(self):
        """Reset container before each test."""
        import interface.api.deps as deps

        deps._container = None
        from infrastructure.di import container as di

        di.reset()

    def teardown_method(self):
        """Clean up container after each test."""
        import interface.api.deps as deps

        deps._container = None
        from infrastructure.di import container as di

        di.reset()

    def test_get_container_raises_503_when_not_initialized(self):
        """get_container should raise 503 when container is None."""
        with pytest.raises(HTTPException) as exc_info:
            get_container()

        assert exc_info.value.status_code == 503
        assert "not initialized" in exc_info.value.detail.lower()
        assert "server logs" in exc_info.value.detail.lower()

    def test_get_container_returns_container_when_initialized(self):
        """get_container should return container when initialized."""
        ns = SimpleNamespace()
        set_container(ns)

        result = get_container()
        assert result is ns

    def test_get_datalake_gateway_returns_gateway(self):
        """get_datalake_gateway should return the gateway."""
        mock_gateway = MagicMock()
        initialize_all_services(datalake_gateway=mock_gateway)

        assert get_datalake_gateway() is mock_gateway

    def test_get_view_manager_returns_manager(self):
        """get_view_manager should return the ViewManager."""
        mock_vm = MagicMock()
        initialize_all_services(view_manager=mock_vm)

        assert get_view_manager() is mock_vm

    def test_get_data_catalog_returns_catalog(self):
        """get_data_catalog should return the DataCatalog."""
        mock_catalog = MagicMock()
        initialize_all_services(data_catalog=mock_catalog)

        assert get_data_catalog() is mock_catalog

    def test_get_event_bus_returns_bus(self):
        """get_event_bus should return the EventBus."""
        event_bus = EventBus()
        initialize_all_services(event_bus=event_bus)

        assert get_event_bus() is event_bus

    def test_get_broker_service_returns_service(self):
        """get_broker_service should return the BrokerService."""
        mock_broker = MagicMock()
        initialize_all_services(broker_service=mock_broker)

        assert get_broker_service() is mock_broker

    def test_get_trading_context_error_message_is_actionable(self):
        """Error message should tell user how to fix the issue."""
        # First initialize container with None trading_context
        initialize_all_services()  # Creates container but trading_context is None

        with pytest.raises(HTTPException) as exc_info:
            get_trading_context()

        detail = exc_info.value.detail
        assert "TradingContext not initialized" in detail
        assert "event_bus" in detail.lower() or "trading_context" in detail.lower()

    def test_get_order_manager_error_message_is_actionable(self):
        """Error message should tell user how to fix the issue."""
        # First initialize container with None trading_context
        initialize_all_services()

        with pytest.raises(HTTPException) as exc_info:
            get_order_manager()

        detail = exc_info.value.detail
        assert "OrderManager" in detail or "order" in detail.lower()
        assert "event_bus" in detail.lower() or "trading_context" in detail.lower()

    def test_get_position_manager_error_message_is_actionable(self):
        """Error message should tell user how to fix the issue."""
        # First initialize container with None trading_context
        initialize_all_services()

        with pytest.raises(HTTPException) as exc_info:
            get_position_manager()

        detail = exc_info.value.detail
        assert "PositionManager" in detail or "position" in detail.lower()

    def test_get_risk_manager_error_message_is_actionable(self):
        """Error message should tell user how to fix the issue."""
        # First initialize container with None trading_context
        initialize_all_services()

        with pytest.raises(HTTPException) as exc_info:
            get_risk_manager()

        detail = exc_info.value.detail
        assert "RiskManager" in detail or "risk" in detail.lower()


class TestDIFallbackBehavior:
    """Test fallback behavior when OMS components not directly registered."""

    def setup_method(self):
        """Reset container before each test."""
        import interface.api.deps as deps

        deps._container = None
        from infrastructure.di import container as di

        di.reset()

    def teardown_method(self):
        """Clean up container after each test."""
        import interface.api.deps as deps

        deps._container = None
        from infrastructure.di import container as di

        di.reset()

    def test_order_manager_falls_back_to_trading_context(self):
        """get_order_manager should fall back to TradingContext.order_manager."""
        event_bus = EventBus()
        ctx = build_test_trading_context(event_bus=event_bus)

        # Initialize with trading_context but NOT direct order_manager
        initialize_all_services(
            event_bus=event_bus,
            trading_context=ctx,
        )

        result = get_order_manager()
        assert result is ctx.order_manager

    def test_position_manager_falls_back_to_trading_context(self):
        """get_position_manager should fall back to TradingContext.position_manager."""
        event_bus = EventBus()
        ctx = build_test_trading_context(event_bus=event_bus)

        initialize_all_services(
            event_bus=event_bus,
            trading_context=ctx,
        )

        result = get_position_manager()
        assert result is ctx.position_manager

    def test_risk_manager_falls_back_to_trading_context(self):
        """get_risk_manager should fall back to TradingContext.risk_manager."""
        event_bus = EventBus()
        ctx = build_test_trading_context(event_bus=event_bus)

        initialize_all_services(
            event_bus=event_bus,
            trading_context=ctx,
        )

        result = get_risk_manager()
        assert result is ctx.risk_manager

    def test_direct_registration_takes_precedence(self):
        """Directly registered manager should take precedence over TradingContext."""
        event_bus = EventBus()
        ctx = build_test_trading_context(event_bus=event_bus)
        mock_order_manager = MagicMock()

        initialize_all_services(
            event_bus=event_bus,
            trading_context=ctx,
            order_manager=mock_order_manager,
        )

        result = get_order_manager()
        assert result is mock_order_manager  # Should use direct, not ctx.order_manager


class TestThreadSafety:
    """Test thread-safe container access."""

    def setup_method(self):
        """Reset container before each test."""
        import interface.api.deps as deps

        deps._container = None
        from infrastructure.di import container as di

        di.reset()

    def teardown_method(self):
        """Clean up container after each test."""
        import interface.api.deps as deps

        deps._container = None
        from infrastructure.di import container as di

        di.reset()

    def test_concurrent_reads_are_safe(self):
        """Multiple threads reading container should not crash."""
        import threading

        event_bus = EventBus()
        initialize_all_services(event_bus=event_bus)

        errors = []

        def read_container():
            try:
                for _ in range(100):
                    container = get_container()
                    assert container is not None
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_container) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread safety errors: {errors}"

    def test_concurrent_get_trading_context_is_safe(self):
        """Multiple threads getting TradingContext should not crash."""
        import threading

        event_bus = EventBus()
        ctx = build_test_trading_context(event_bus=event_bus)
        initialize_all_services(event_bus=event_bus, trading_context=ctx)

        errors = []

        def get_ctx():
            try:
                for _ in range(100):
                    result = get_trading_context()
                    assert result is ctx
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get_ctx) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread safety errors: {errors}"
