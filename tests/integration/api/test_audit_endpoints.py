"""Tests for audit trail API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from interface.api.config import APIConfig
from interface.api.main import create_app
from application.audit import audit_logger


@pytest.fixture(autouse=True)
def _clear_audit_store() -> None:
    audit_logger.store.clear()
    yield
    audit_logger.store.clear()


@pytest.fixture
def client() -> TestClient:
    app = create_app(config=APIConfig(auth_mode="none"))
    return TestClient(app)


class TestAuditEndpoints:
    def test_audit_routes_are_registered(self, client: TestClient) -> None:
        paths = client.app.openapi()["paths"]
        assert "/api/v1/audit/events" in paths
        assert "/api/v1/audit/stats" in paths
        assert "/api/v1/audit/events/{event_id}" in paths

    def test_list_events_empty(self, client: TestClient) -> None:
        response = client.get("/api/v1/audit/events")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_events_returns_logged_event(self, client: TestClient) -> None:
        event = audit_logger.log(
            event_type="order.placed",
            actor="user:test",
            action="create",
            resource_type="order",
            resource_id="ORD-1",
            details={"symbol": "RELIANCE"},
        )

        response = client.get("/api/v1/audit/events")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["event_id"] == event.event_id
        assert body[0]["event_type"] == "order.placed"
        assert body[0]["details"]["symbol"] == "RELIANCE"

    def test_get_event_by_id(self, client: TestClient) -> None:
        event = audit_logger.log(
            event_type="order.cancelled",
            actor="user:test",
            action="cancel",
            resource_type="order",
            resource_id="ORD-2",
        )

        response = client.get(f"/api/v1/audit/events/{event.event_id}")
        assert response.status_code == 200
        assert response.json()["resource_id"] == "ORD-2"

    def test_get_event_by_id_not_found(self, client: TestClient) -> None:
        response = client.get("/api/v1/audit/events/missing-id")
        assert response.status_code == 404

    def test_stats_endpoint(self, client: TestClient) -> None:
        audit_logger.log(
            event_type="order.placed",
            actor="user:a",
            action="create",
            resource_type="order",
            resource_id="ORD-1",
        )
        audit_logger.log(
            event_type="order.placed",
            actor="user:b",
            action="create",
            resource_type="order",
            resource_id="ORD-2",
        )
        audit_logger.log(
            event_type="order.cancelled",
            actor="user:a",
            action="cancel",
            resource_type="order",
            resource_id="ORD-1",
        )

        response = client.get("/api/v1/audit/stats")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert body["by_event_type"]["order.placed"] == 2
        assert body["by_event_type"]["order.cancelled"] == 1
