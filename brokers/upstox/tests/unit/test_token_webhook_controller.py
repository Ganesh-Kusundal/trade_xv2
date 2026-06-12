from __future__ import annotations

import json
from unittest.mock import MagicMock

from brokers.upstox.auth.config import UpstoxConnectionSettings
from brokers.upstox.auth.token_webhook_controller import UpstoxTokenWebhookController


def test_webhook_applied_on_valid_payload():
    UpstoxConnectionSettings(client_id="CID", access_token="x")
    mgr = MagicMock()
    mgr.upgrade_from_webhook.return_value = True
    controller = UpstoxTokenWebhookController(mgr)
    result = controller.handle(
        json.dumps({"access_token": "abc", "authorization_expiry": "1740729366039"})
    )
    assert result.applied is True
    assert result.expires_at_ms == 1740729366039


def test_webhook_rejected_on_missing_access_token():
    controller = UpstoxTokenWebhookController(MagicMock())
    result = controller.handle(json.dumps({"authorization_expiry": "123"}))
    assert result.applied is False
    assert "access_token" in result.reason


def test_webhook_rejected_on_missing_expiry():
    controller = UpstoxTokenWebhookController(MagicMock())
    result = controller.handle(json.dumps({"access_token": "x"}))
    assert result.applied is False
    assert "authorization_expiry" in result.reason


def test_webhook_rejected_on_non_numeric_expiry():
    controller = UpstoxTokenWebhookController(MagicMock())
    result = controller.handle(
        json.dumps({"access_token": "x", "authorization_expiry": "not-a-number"})
    )
    assert result.applied is False
    assert "numeric" in result.reason


def test_webhook_rejected_on_empty_body():
    controller = UpstoxTokenWebhookController(MagicMock())
    assert controller.handle("").applied is False
    assert controller.handle("   ").applied is False
    assert controller.handle(None).applied is False


def test_webhook_rejected_when_incoming_not_fresher():
    UpstoxConnectionSettings(client_id="CID", access_token="x")
    mgr = MagicMock()
    mgr.upgrade_from_webhook.return_value = False
    controller = UpstoxTokenWebhookController(mgr)
    result = controller.handle(json.dumps({"access_token": "x", "authorization_expiry": "1"}))
    assert result.applied is False
    assert "not fresher" in result.reason
