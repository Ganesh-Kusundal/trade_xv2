"""Webhook HMAC verification."""

from __future__ import annotations

import json

import pytest

from infrastructure.security.webhook_auth import (
    WebhookAuthError,
    compute_webhook_signature,
    verify_webhook_signature,
)


def test_valid_signature_passes(monkeypatch) -> None:
    monkeypatch.setenv("UPSTOX_WEBHOOK_SECRET", "test-secret")
    body = json.dumps({"message_type": "access_token"}).encode()
    sig = compute_webhook_signature(body, "test-secret")
    verify_webhook_signature(body, sig)


def test_invalid_signature_rejected(monkeypatch) -> None:
    monkeypatch.setenv("UPSTOX_WEBHOOK_SECRET", "test-secret")
    body = b"{}"
    with pytest.raises(WebhookAuthError, match="invalid"):
        verify_webhook_signature(body, "deadbeef")


def test_production_requires_secret(monkeypatch) -> None:
    monkeypatch.setenv("TRADEX_ENV", "production")
    monkeypatch.delenv("UPSTOX_WEBHOOK_SECRET", raising=False)
    with pytest.raises(WebhookAuthError, match="required"):
        verify_webhook_signature(b"{}", None)
