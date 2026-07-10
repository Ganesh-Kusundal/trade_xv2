"""Contract tests for Upstox webhook token callback route."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.config import APIConfig
from api.deps import reset_container
from api.main import create_app


@pytest.fixture
def upstox_test_setup():
    """Setup a test app instance with a mocked Upstox broker stack."""
    reset_container()

    mock_token_manager = MagicMock()
    mock_broker = SimpleNamespace(_token_manager=mock_token_manager)
    mock_gateway = SimpleNamespace(_broker=mock_broker)
    broker_service = SimpleNamespace(
        active_broker=mock_gateway,
        active_broker_name="upstox",
    )

    # Enable standard api_key auth to verify the webhook bypasses authentication
    app = create_app(
        config=APIConfig(auth_mode="api_key", api_key="test-api-key"),
        broker_service=broker_service,
    )
    client = TestClient(app)
    yield client, mock_token_manager
    reset_container()


def test_webhook_bypasses_authentication(upstox_test_setup) -> None:
    """Verify webhook callback is public and does not require X-API-Key auth."""
    client, _ = upstox_test_setup

    # Standard protected live routes should fail with 401 Unauthorized
    resp_protected = client.get("/api/v1/live/profile")
    assert resp_protected.status_code == 401

    # Webhook callback should bypass 401 auth and hit validation logic instead (yielding 422 here due to empty payload)
    resp_webhook = client.post("/api/v1/live/upstox/token-callback", json={})
    assert resp_webhook.status_code == 422


def test_webhook_successful_upgrade(upstox_test_setup) -> None:
    """Verify successful access token delivery upgrades the token state."""
    client, mock_token_manager = upstox_test_setup
    mock_token_manager.upgrade_from_webhook.return_value = True

    now_ms = int(time.time() * 1000)
    payload = {
        "message_type": "access_token",
        "client_id": "test-client-id",
        "user_id": "UCC1234",
        "access_token": "new-test-access-token",
        "token_type": "Bearer",
        "expires_at": str(now_ms + 3600 * 1000),
        "issued_at": str(now_ms),
    }

    resp = client.post("/api/v1/live/upstox/token-callback", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"status": "success", "detail": "token_upgraded"}

    mock_token_manager.upgrade_from_webhook.assert_called_once_with(
        access_token="new-test-access-token",
        expires_at_ms=now_ms + 3600 * 1000,
    )


def test_webhook_skipped_upgrade_stale_token(upstox_test_setup) -> None:
    """Verify callback handles stale/older tokens gracefully by skipping them."""
    client, mock_token_manager = upstox_test_setup
    mock_token_manager.upgrade_from_webhook.return_value = False

    payload = {
        "message_type": "access_token",
        "client_id": "test-client-id",
        "user_id": "UCC1234",
        "access_token": "old-stale-token",
        "token_type": "Bearer",
        "expires_at": "1000000000000",
    }

    resp = client.post("/api/v1/live/upstox/token-callback", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"status": "skipped", "detail": "token_is_stale"}


def test_webhook_invalid_message_type(upstox_test_setup) -> None:
    """Verify requests with message_types other than 'access_token' are rejected."""
    client, _ = upstox_test_setup

    payload = {
        "message_type": "some_other_event",
        "client_id": "test-client-id",
        "user_id": "UCC1234",
        "access_token": "token",
        "expires_at": "1731412800000",
    }

    resp = client.post("/api/v1/live/upstox/token-callback", json=payload)
    assert resp.status_code == 400
    assert "Invalid message_type" in resp.json()["detail"]


def test_webhook_non_upstox_broker_active() -> None:
    """Verify endpoint returns 400 if the active broker is not Upstox."""
    reset_container()

    # Active broker set as "dhan"
    broker_service = SimpleNamespace(
        active_broker=MagicMock(),
        active_broker_name="dhan",
    )
    app = create_app(config=APIConfig(auth_mode="none"), broker_service=broker_service)
    client = TestClient(app)

    payload = {
        "message_type": "access_token",
        "client_id": "test-client-id",
        "user_id": "UCC1234",
        "access_token": "token",
        "expires_at": "1731412800000",
    }

    resp = client.post("/api/v1/live/upstox/token-callback", json=payload)
    assert resp.status_code == 400
    assert "expected upstox" in resp.json()["detail"]

    reset_container()
