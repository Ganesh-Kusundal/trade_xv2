"""Webhook request authenticity — HMAC signature verification."""

from __future__ import annotations

import hashlib
import hmac
import os
import time

from domain.exceptions import TradeXV2Error


class WebhookAuthError(TradeXV2Error):
    """Webhook failed signature or replay checks."""


def _is_production_env() -> bool:
    env = (os.getenv("TRADEX_ENV") or "development").strip().lower()
    return env in ("production", "staging")


def webhook_secret_configured() -> bool:
    return bool(os.getenv("UPSTOX_WEBHOOK_SECRET", "").strip())


def compute_webhook_signature(body: bytes, secret: str) -> str:
    """HMAC-SHA256 hex digest of the raw request body."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_webhook_signature(
    body: bytes,
    signature: str | None,
    *,
    secret: str | None = None,
    issued_at_ms: int | None = None,
    max_age_seconds: int = 300,
) -> None:
    """Verify webhook HMAC and optional replay window.

    Raises:
        WebhookAuthError: when signature is missing, invalid, or stale.
    """
    configured = (secret or os.getenv("UPSTOX_WEBHOOK_SECRET", "")).strip()
    if not configured:
        if _is_production_env():
            raise WebhookAuthError("UPSTOX_WEBHOOK_SECRET is required in production")
        return

    if not signature or not signature.strip():
        raise WebhookAuthError("missing X-Webhook-Signature header")

    expected = compute_webhook_signature(body, configured)
    if not hmac.compare_digest(signature.strip().lower(), expected.lower()):
        raise WebhookAuthError("invalid webhook signature")

    if issued_at_ms is not None and max_age_seconds > 0:
        now_ms = int(time.time() * 1000)
        if now_ms - issued_at_ms > max_age_seconds * 1000:
            raise WebhookAuthError("webhook issued_at is outside replay window")