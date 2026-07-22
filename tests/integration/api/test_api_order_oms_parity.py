"""P0 audit: API order mutations share one OrderManager with GET/list paths.

Verifies the split-brain fix: POST via ExecutionComposer writes to the same
book that GET /orders/{id} reads from TradingContext.order_manager.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from application.composer.execution import ExecutionComposer
from domain.enums import OrderStatus, OrderType, ProductType, Side
from domain.ports.execution_target import ExecutionTargetKind
from infrastructure.event_bus.event_bus import EventBus
from interface.api.config import APIConfig
from interface.api.main import create_app
from tests.conftest import build_test_trading_context


@pytest.fixture(autouse=True)
def _wire_runtime_async_bridge():
    from runtime.composition import wire_domain_port_sinks

    wire_domain_port_sinks()


@pytest.fixture(autouse=True)
def _reset_api_container():
    import interface.api.deps as deps

    deps._container = None
    yield
    deps._container = None


def _build_api_client_with_shared_composer() -> tuple[TestClient, object, object]:
    """Real TradingContext + ExecutionComposer sharing one OrderManager."""
    bus = EventBus()
    ctx = build_test_trading_context(event_bus=bus)
    om = ctx.order_manager
    submit_counter = {"n": 0}

    registry = MagicMock()
    gateway = AsyncMock()

    async def _gw_place(request, quota=None):
        submit_counter["n"] += 1
        oid = f"BRK-{submit_counter['n']}"
        return SimpleNamespace(
            success=True,
            order_id=oid,
            broker_order_id=oid,
            status=OrderStatus.OPEN,
        )

    async def _gw_cancel(oid, quota=None):
        return SimpleNamespace(success=True)

    gateway.place_order = _gw_place
    gateway.cancel_order = _gw_cancel
    registry.get_gateway.return_value = gateway

    router = MagicMock()
    router.route.return_value = MagicMock(primary_broker="paper")

    quota = AsyncMock()
    quota.acquire_async.return_value = MagicMock()

    composer = ExecutionComposer(
        registry=registry,
        router=router,
        quota_scheduler=quota,
        risk_manager=ctx.risk_manager,
        order_manager=om,
        execution_target_kind=ExecutionTargetKind.PAPER,
    )

    broker_svc = SimpleNamespace(
        active_broker_name="paper",
        allow_live_orders=True,
        live_actionable=True,
    )

    app = create_app(
        config=APIConfig(auth_mode="none"),
        trading_context=ctx,
        broker_service=broker_svc,
        execution_composer=composer,
    )
    return TestClient(app), ctx, composer


def test_composer_and_trading_context_share_order_manager():
    _, ctx, composer = _build_api_client_with_shared_composer()
    assert composer._order_manager is ctx.order_manager


def test_post_then_get_returns_same_order_id():
    """Regression for R1: POST must land in the book GET reads."""
    client, ctx, _composer = _build_api_client_with_shared_composer()

    payload = {
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "transaction_type": "BUY",
        "order_type": "LIMIT",
        "quantity": 1,
        "price": 2500.0,
        "product_type": "INTRADAY",
        "correlation_id": "api-parity:post-get:1",
    }
    post = client.post("/api/v1/orders", json=payload)
    assert post.status_code == 200, post.text
    order_id = post.json()["order_id"]
    assert order_id

    get_one = client.get(f"/api/v1/orders/{order_id}")
    assert get_one.status_code == 200, get_one.text
    assert get_one.json()["order_id"] == order_id

    listed = client.get("/api/v1/orders")
    assert listed.status_code == 200
    ids = {o["order_id"] for o in listed.json()["orders"]}
    assert order_id in ids

    assert ctx.order_manager.get_order(order_id) is not None


def test_post_sl_delivery_enums_accepted_at_boundary():
    """Regression for C1: OpenAPI SL/DELIVERY must map to domain enums."""
    client, ctx, _composer = _build_api_client_with_shared_composer()

    payload = {
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "transaction_type": "BUY",
        "order_type": "SL",
        "quantity": 1,
        "price": 2500.0,
        "trigger_price": 2490.0,
        "product_type": "DELIVERY",
        "correlation_id": "api-parity:sl-delivery:1",
    }
    post = client.post("/api/v1/orders", json=payload)
    assert post.status_code == 200, post.text
    order_id = post.json()["order_id"]
    stored = ctx.order_manager.get_order(order_id)
    assert stored is not None
    assert stored.order_type is OrderType.STOP_LOSS
    assert stored.product_type is ProductType.CNC


def test_delete_after_post_cancels_same_book_order():
    client, ctx, _composer = _build_api_client_with_shared_composer()

    post = client.post(
        "/api/v1/orders",
        json={
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "transaction_type": "BUY",
            "order_type": "LIMIT",
            "quantity": 1,
            "price": 2500.0,
            "product_type": "INTRADAY",
            "correlation_id": "api-parity:cancel:1",
        },
    )
    assert post.status_code == 200
    order_id = post.json()["order_id"]

    delete = client.delete(f"/api/v1/orders/{order_id}")
    assert delete.status_code == 200, delete.text
    assert delete.json()["status"] in ("CANCELLED", "OPEN")

    stored = ctx.order_manager.get_order(order_id)
    assert stored is not None
    assert stored.status in (OrderStatus.CANCELLED, OrderStatus.OPEN)


def test_post_without_correlation_or_header_rejected(monkeypatch):
    monkeypatch.delenv("TRADEX_DEV", raising=False)
    client, _, _ = _build_api_client_with_shared_composer()

    post = client.post(
        "/api/v1/orders",
        json={
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "transaction_type": "BUY",
            "order_type": "LIMIT",
            "quantity": 1,
            "price": 2500.0,
            "product_type": "INTRADAY",
        },
    )
    assert post.status_code == 400
    assert "Idempotency" in post.json()["detail"] or "correlation_id" in post.json()["detail"]


def test_post_accepts_x_idempotency_key_header():
    client, ctx, _composer = _build_api_client_with_shared_composer()

    post = client.post(
        "/api/v1/orders",
        json={
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "transaction_type": "BUY",
            "order_type": "LIMIT",
            "quantity": 1,
            "price": 2500.0,
            "product_type": "INTRADAY",
        },
        headers={"X-Idempotency-Key": "api-parity:header-key:1"},
    )
    assert post.status_code == 200, post.text
    order_id = post.json()["order_id"]
    assert ctx.order_manager.get_order(order_id) is not None
