"""Tests for ExtendedOrderService extension registry integration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.oms.extended_order_service import (
    ExtendedOrderResult,
    ExtendedOrderService,
    ExtendedFeatureUnavailableError,
)


class TestExtendedOrderServiceExtensionRegistry:
    """Test ExtensionRegistry integration in ExtendedOrderService."""

    @pytest.fixture
    def mock_risk_manager(self) -> MagicMock:
        """Create a mock risk manager."""
        rm = MagicMock()
        rm.is_kill_switch_active.return_value = False
        return rm

    @pytest.fixture
    def mock_event_bus(self) -> MagicMock:
        """Create a mock event bus."""
        return MagicMock()

    @pytest.fixture
    def mock_broker_service(self) -> MagicMock:
        """Create a mock broker service."""
        bs = MagicMock()
        bs.active_broker_name = "dhan"
        return bs

    @pytest.fixture
    def mock_extension_registry(self) -> MagicMock:
        """Create a mock extension registry."""
        return MagicMock()

    @pytest.fixture
    def service_with_registry(
        self,
        mock_risk_manager: MagicMock,
        mock_event_bus: MagicMock,
        mock_broker_service: MagicMock,
        mock_extension_registry: MagicMock,
    ) -> ExtendedOrderService:
        """Create ExtendedOrderService with extension registry."""
        return ExtendedOrderService(
            risk_manager=mock_risk_manager,
            event_bus=mock_event_bus,
            broker_service=mock_broker_service,
            extension_registry=mock_extension_registry,
        )

    @pytest.fixture
    def service_without_registry(
        self,
        mock_risk_manager: MagicMock,
        mock_event_bus: MagicMock,
        mock_broker_service: MagicMock,
    ) -> ExtendedOrderService:
        """Create ExtendedOrderService without extension registry (legacy)."""
        return ExtendedOrderService(
            risk_manager=mock_risk_manager,
            event_bus=mock_event_bus,
            broker_service=mock_broker_service,
        )

    def test_require_extension_returns_extension(
        self,
        service_with_registry: ExtendedOrderService,
        mock_extension_registry: MagicMock,
    ) -> None:
        """Test that _require_extension returns extension from registry."""
        mock_provider = MagicMock()
        mock_extension_registry.require.return_value = mock_provider

        result = service_with_registry._require_extension(MagicMock)

        assert result is mock_provider
        mock_extension_registry.require.assert_called_once_with("dhan", MagicMock)

    def test_require_extension_raises_without_registry(
        self,
        service_without_registry: ExtendedOrderService,
    ) -> None:
        """Test that _require_extension raises when registry is None."""
        with pytest.raises(ExtendedFeatureUnavailableError) as exc_info:
            service_without_registry._require_extension(MagicMock)

        assert "ExtensionRegistry not configured" in str(exc_info.value)

    def test_executor_resolves_via_registry(
        self,
        service_with_registry: ExtendedOrderService,
        mock_extension_registry: MagicMock,
    ) -> None:
        """_executor() resolves OrderCapabilityPort by broker id (DR-B1 / TOS-P3-002)."""
        from domain.extensions.order_capability import OrderCapabilityPort

        mock_executor = MagicMock()
        mock_extension_registry.require.return_value = mock_executor

        result = service_with_registry._executor()

        assert result is mock_executor
        mock_extension_registry.require.assert_called_once_with(
            "dhan", OrderCapabilityPort
        )

    def test_constructor_accepts_extension_registry(
        self,
        mock_risk_manager: MagicMock,
        mock_event_bus: MagicMock,
        mock_broker_service: MagicMock,
        mock_extension_registry: MagicMock,
    ) -> None:
        """Test that constructor accepts extension_registry parameter."""
        service = ExtendedOrderService(
            risk_manager=mock_risk_manager,
            event_bus=mock_event_bus,
            broker_service=mock_broker_service,
            extension_registry=mock_extension_registry,
        )

        assert service._extensions is mock_extension_registry

    def test_constructor_defaults_extension_registry_to_none(
        self,
        mock_risk_manager: MagicMock,
        mock_event_bus: MagicMock,
        mock_broker_service: MagicMock,
    ) -> None:
        """Test that extension_registry defaults to None."""
        service = ExtendedOrderService(
            risk_manager=mock_risk_manager,
            event_bus=mock_event_bus,
            broker_service=mock_broker_service,
        )

        assert service._extensions is None
