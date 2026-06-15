"""HTTP controller for Upstox's Access Token Request webhook (Flow 2).

Mirrors Trade_J ``UpstoxTokenWebhookController``. The composition layer wires
this to a Flask route / aiohttp handler / FastAPI endpoint.

Payload shape::

    POST /upstox/token-webhook
    {
      "access_token": "...",
      "authorization_expiry": "1740729366039"
    }
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from .token_manager import UpstoxTokenManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebhookResult:
    applied: bool = False
    expires_at_ms: int = 0
    reason: str = ""

    @classmethod
    def accepted(cls, expires_at_ms: int) -> WebhookResult:
        return cls(applied=True, expires_at_ms=expires_at_ms, reason="")

    @classmethod
    def rejected(cls, reason: str) -> WebhookResult:
        return cls(applied=False, expires_at_ms=0, reason=reason)


class UpstoxTokenWebhookController:
    def __init__(
        self,
        token_manager: UpstoxTokenManager,
        source_label: str = "upstox",
    ) -> None:
        self._token_manager = token_manager
        self._source_label = source_label

    @property
    def token_manager(self) -> UpstoxTokenManager:
        return self._token_manager

    def handle(self, json_body: str) -> WebhookResult:
        if not json_body or not json_body.strip():
            return WebhookResult.rejected("empty body")
        try:
            payload = json.loads(json_body)
        except (ValueError, TypeError) as exc:
            return WebhookResult.rejected(f"parse error: {exc}")

        access_token = payload.get("access_token") if isinstance(payload, dict) else None
        auth_expiry = payload.get("authorization_expiry") if isinstance(payload, dict) else None
        if not access_token or not isinstance(access_token, str):
            return WebhookResult.rejected("missing access_token")
        if not auth_expiry or not isinstance(auth_expiry, str):
            return WebhookResult.rejected("missing authorization_expiry")
        try:
            expires_at_ms = int(auth_expiry)
        except ValueError:
            return WebhookResult.rejected("authorization_expiry is not a numeric epoch ms")
        try:
            applied = self._token_manager.upgrade_from_webhook(
                access_token=access_token, expires_at_ms=expires_at_ms
            )
        except ValueError as exc:
            return WebhookResult.rejected(str(exc))
        if applied:
            logger.info(
                "Upstox token upgraded via webhook[%s]: expiresAt=%d",
                self._source_label,
                expires_at_ms,
            )
            return WebhookResult.accepted(expires_at_ms)
        return WebhookResult.rejected("incoming token not fresher than current state")
