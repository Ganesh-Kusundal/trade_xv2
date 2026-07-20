"""API order mutation routes must pass the live-order authority."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from application.oms import OrderRequest
from domain import OrderType, Side
from domain.events.types import EventType
from infrastructure.event_bus.event_bus import EventBus
from interface.api.config import APIConfig
from interface.api.main import create_app
from tests.conftest import build_test_trading_context


@pytest.fixture(autouse=True)
def _reset_api_container():
    import interface.api.deps as deps

    deps._container = None
    yield
    deps._container = None


def _order_payload() -> dict[str, object]:
    return {
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "transaction_type": "BUY",
        "order_type": "LIMIT",
        "quantity": 10,
        "price": 2500.0,
        "product_type": "INTRADAY",
    }


def _build_client_with_order(
    *,
    allow_live_orders: bool = True,
    broker_name: str = "paper",
) -> tuple[TestClient, str]:
    bus = EventBus()
    ctx = build_test_trading_context(event_bus=bus)
    placed = ctx.order_manager.place_order(
        OrderRequest(
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
            price=Decimal("2500"),
            order_type=OrderType.LIMIT,
        )
    )
    assert placed.success and placed.order is not None
    order_id = placed.order.order_id

    broker_svc = SimpleNamespace(
        active_broker_name=broker_name,
        allow_live_orders=allow_live_orders,
        live_actionable=True,
    )
    mock_composer = MagicMock()
    mock_composer.modify_order = AsyncMock(return_value=SimpleNamespace(success=True))
    mock_composer.cancel_order = AsyncMock(return_value=SimpleNamespace(success=True))
    app = create_app(
        config=APIConfig(auth_mode="none"),
        trading_context=ctx,
        broker_service=broker_svc,
        execution_composer=mock_composer,
    )
    return TestClient(app), order_id


def test_modify_order_routes_through_authorize_live_order() -> None:
    client, order_id = _build_client_with_order()
    calls: list[dict[str, object]] = []

    def _capture(**kwargs: object) -> None:
        calls.append(kwargs)

    with patch(
        "interface.api.deps.authorize_live_order",
        side_effect=_capture,
    ):
        response = client.put(f"/api/v1/orders/{order_id}", json=_order_payload())

    assert response.status_code in (200, 400)
    assert len(calls) == 1
    assert calls[0]["mutation_action"] == "modify"
    assert calls[0]["risk_payload"] is not None


def test_cancel_order_routes_through_authorize_live_order() -> None:
    client, order_id = _build_client_with_order()
    calls: list[dict[str, object]] = []

    def _capture(**kwargs: object) -> None:
        calls.append(kwargs)

    with patch(
        "interface.api.deps.authorize_live_order",
        side_effect=_capture,
    ):
        response = client.delete(f"/api/v1/orders/{order_id}")

    assert response.status_code in (200, 400)
    assert len(calls) == 1
    assert calls[0]["mutation_action"] == "cancel"


def test_modify_order_blocked_when_authority_rejects() -> None:
    client, order_id = _build_client_with_order(
        allow_live_orders=False,
        broker_name="dhan",
    )

    response = client.put(f"/api/v1/orders/{order_id}", json=_order_payload())

    assert response.status_code == 403
    assert "allow_live_orders" in response.json()["detail"].lower()


def test_cancel_order_blocked_when_authority_rejects() -> None:
    client, order_id = _build_client_with_order(
        allow_live_orders=False,
        broker_name="dhan",
    )

    response = client.delete(f"/api/v1/orders/{order_id}")

    assert response.status_code == 403
    assert "allow_live_orders" in response.json()["detail"].lower()


def test_reconciliation_reattach_unsubscribes_by_token() -> None:
    """ARCH-007: attach_reconciliation_service stores subscribe tokens."""
    from tests.component.oms.test_reconciliation_attach import StubReconciliationService

    ctx = build_test_trading_context()
    stub = StubReconciliationService()
    ctx.attach_reconciliation_service(stub)
    assert all(isinstance(token, str) for token in ctx._recon_handlers)
    before = ctx._event_bus.subscriber_count(EventType.ORDER_UPDATED.value)
    ctx.attach_reconciliation_service(StubReconciliationService())
    after = ctx._event_bus.subscriber_count(EventType.ORDER_UPDATED.value)
    assert after == before
    ctx.stop_reconciliation()
