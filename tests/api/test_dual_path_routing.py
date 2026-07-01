"""Task 5 verification: Dual-path routing in orders API.

Tests that the COMPOSER_EXECUTION feature flag correctly controls
which execution path is used for place_order and cancel_order:
- Path A (flag OFF): Legacy ExecutionService via OMS
- Path B (flag ON): ExecutionComposer with multi-broker routing
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.config import APIConfig
from api.deps import di_container, reset_container
from api.main import create_app
from config.feature_flags import FeatureFlags


@pytest.fixture(autouse=True)
def _clean_state():
    """Reset DI container and feature flags before/after each test."""
    reset_container()
    FeatureFlags.reset()
    yield
    FeatureFlags.reset()
    reset_container()


def _make_app(
    composer=None,
    execution_service=None,
    extra_di=None,
):
    """Create test app with mocked broker_service.

    ``create_app`` already registers services via ``initialize_all_services``,
    but the camelCase key (``brokerService``) doesn't match the snake_case
    resolve key (``broker_service``), so we re-register with the correct key.
    ``extra_di`` allows registering additional services (e.g. order_manager).
    """
    mock_broker_service = MagicMock()
    mock_exec_svc = execution_service or MagicMock()
    mock_broker_service.execution_service = mock_exec_svc

    app = create_app(
        config=APIConfig(auth_mode="none"),
        broker_service=mock_broker_service,
        execution_composer=composer,
    )

    # Re-register broker_service with the snake_case key that
    # get_broker_service() actually resolves.
    di_container.register_instance("broker_service", mock_broker_service)

    # Register any extra DI services needed by endpoints
    if extra_di:
        for name, value in extra_di.items():
            di_container.register_instance(name, value)

    return app, mock_broker_service, mock_exec_svc


def _order_payload(**overrides):
    base = {
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "transaction_type": "BUY",
        "order_type": "MARKET",
        "quantity": 10,
    }
    base.update(overrides)
    return base


# ── place_order ──────────────────────────────────────────────────────


class TestPlaceOrderDualPath:
    """Verify place_order routes through correct path based on feature flag."""

    def test_flag_off_uses_legacy_execution_service(self):
        """Flag OFF → Path A: legacy ExecutionService.

        A composer must still be registered in DI so the dependency
        doesn't raise 503 before the endpoint runs; the flag being OFF
        ensures the legacy path is selected.
        """
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.order_id = "LEGACY-001"

        mock_exec_svc = MagicMock()
        mock_exec_svc.place_order.return_value = mock_result

        # Provide a no-op composer to satisfy the dependency
        mock_composer = AsyncMock()

        app, _, _ = _make_app(
            composer=mock_composer,
            execution_service=mock_exec_svc,
        )
        client = TestClient(app)

        assert not FeatureFlags.is_enabled("COMPOSER_EXECUTION")
        response = client.post("/api/v1/orders", json=_order_payload())

        mock_exec_svc.place_order.assert_called_once()
        mock_composer.place_order.assert_not_called()
        assert response.status_code == 200
        assert response.json()["order_id"] == "LEGACY-001"

    def test_flag_on_uses_composer(self):
        """Flag ON + composer available → Path B: ExecutionComposer."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.order_id = "COMPOSER-001"
        mock_result.status = "PENDING"

        mock_composer = AsyncMock()
        mock_composer.place_order.return_value = mock_result

        app, _, mock_exec_svc = _make_app(composer=mock_composer)
        client = TestClient(app)

        FeatureFlags.set_flag("COMPOSER_EXECUTION", True)
        response = client.post("/api/v1/orders", json=_order_payload())

        mock_composer.place_order.assert_called_once()
        mock_exec_svc.place_order.assert_not_called()
        assert response.status_code == 200
        assert response.json()["order_id"] == "COMPOSER-001"

    def test_flag_on_composer_not_registered_raises_503(self):
        """Flag ON but composer not in DI → 503 from dependency."""
        app, _, _ = _make_app()
        client = TestClient(app)

        FeatureFlags.set_flag("COMPOSER_EXECUTION", True)
        response = client.post("/api/v1/orders", json=_order_payload())

        # get_execution_composer() raises 503 when composer not in DI
        assert response.status_code == 503

    def test_flag_off_composer_available_but_ignored(self):
        """Flag OFF → legacy path even when composer exists."""
        mock_composer = AsyncMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.order_id = "LEGACY-002"

        mock_exec_svc = MagicMock()
        mock_exec_svc.place_order.return_value = mock_result

        app, _, _ = _make_app(
            composer=mock_composer,
            execution_service=mock_exec_svc,
        )
        client = TestClient(app)

        assert not FeatureFlags.is_enabled("COMPOSER_EXECUTION")
        response = client.post("/api/v1/orders", json=_order_payload())

        mock_exec_svc.place_order.assert_called_once()
        mock_composer.place_order.assert_not_called()


# ── cancel_order ─────────────────────────────────────────────────────


class TestCancelOrderDualPath:
    """Verify cancel_order routes through correct path based on feature flag."""

    @staticmethod
    def _mock_order_manager():
        """Create a mock order_manager that satisfies get_order_repository."""
        om = MagicMock()
        om.get_order.return_value = None
        return om

    def test_flag_off_uses_legacy_cancel(self):
        """Flag OFF → Path A: legacy ExecutionService cancel.

        A composer must still be registered so the dependency resolves.
        """
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.order_id = "CANCEL-LEGACY"

        mock_exec_svc = MagicMock()
        mock_exec_svc.cancel_order.return_value = mock_result

        mock_composer = AsyncMock()

        app, _, _ = _make_app(
            composer=mock_composer,
            execution_service=mock_exec_svc,
            extra_di={"order_manager": self._mock_order_manager()},
        )
        client = TestClient(app)

        response = client.delete("/api/v1/orders/ORD-123")

        mock_exec_svc.cancel_order.assert_called_once_with("ORD-123")
        mock_composer.cancel_order.assert_not_called()
        assert response.status_code == 200

    def test_flag_on_uses_composer_cancel(self):
        """Flag ON → Path B: ExecutionComposer cancel."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.order_id = "ORD-123"
        mock_result.status = "CANCELLED"

        mock_composer = AsyncMock()
        mock_composer.cancel_order.return_value = mock_result

        mock_exec_svc = MagicMock()

        app, _, mock_exec_svc = _make_app(
            composer=mock_composer,
            execution_service=mock_exec_svc,
            extra_di={"order_manager": self._mock_order_manager()},
        )
        client = TestClient(app)

        FeatureFlags.set_flag("COMPOSER_EXECUTION", True)
        response = client.delete("/api/v1/orders/ORD-123")

        mock_composer.cancel_order.assert_called_once_with("ORD-123")
        mock_exec_svc.cancel_order.assert_not_called()
        assert response.status_code == 200
