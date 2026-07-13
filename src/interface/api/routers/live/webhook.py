"""FastAPI router for receiving Upstox webhook callbacks.

Exposes public callback endpoint for receiving daily generated access tokens.
Production requires HMAC signature verification via UPSTOX_WEBHOOK_SECRET.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from domain.enums import BrokerId
from infrastructure.security.webhook_auth import WebhookAuthError, verify_webhook_signature
from interface.api.deps import get_broker_service

logger = logging.getLogger(__name__)

router = APIRouter()


class _WebhookTokenUpgrader(Protocol):
    """Minimal token-manager surface used by the Upstox webhook (no broker import)."""

    def upgrade_from_webhook(self, *, access_token: str, expires_at_ms: int) -> bool: ...


class UpstoxTokenWebhookPayload(BaseModel):
    """Pydantic schema representing the POST body sent by Upstox webhook."""

    message_type: str = Field(..., description="Message type from Upstox (e.g., 'access_token')")
    client_id: str = Field(..., description="API Key of the developer app")
    user_id: str = Field(..., description="Unique client identifier (UCC)")
    access_token: str = Field(..., description="The generated access token")
    token_type: str | None = Field(None, description="Typically 'Bearer'")
    expires_at: str = Field(..., description="Expiration epoch timestamp in milliseconds")
    issued_at: str | None = Field(None, description="Issued epoch timestamp in milliseconds")


def get_upstox_token_manager(
    broker_service: Any = Depends(get_broker_service),
) -> _WebhookTokenUpgrader:
    """Resolve the active broker's token manager without importing broker packages."""
    if broker_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Broker service is not configured",
        )

    active_name = getattr(broker_service, "active_broker_name", None)
    if active_name != BrokerId.UPSTOX:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Active broker is {active_name}, expected upstox",
        )

    gateway = getattr(broker_service, "active_broker", None)
    if gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Active broker is not initialized",
        )

    broker = getattr(gateway, "_broker", None)
    if broker is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Underlying broker is not initialized",
        )

    token_manager = getattr(broker, "_token_manager", None)
    if token_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token manager is not initialized",
        )

    return token_manager


@router.post("/upstox/token-callback")
async def upstox_token_callback(
    request: Request,
    token_manager: _WebhookTokenUpgrader = Depends(get_upstox_token_manager),
) -> dict[str, str]:
    """Public webhook callback for Upstox daily access token delivery."""
    body = await request.body()
    try:
        payload = UpstoxTokenWebhookPayload.model_validate_json(body)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid webhook payload: {exc}",
        ) from exc

    issued_at_ms: int | None = None
    if payload.issued_at:
        try:
            issued_at_ms = int(payload.issued_at)
        except (ValueError, TypeError):
            issued_at_ms = None

    try:
        verify_webhook_signature(
            body,
            request.headers.get("X-Webhook-Signature"),
            issued_at_ms=issued_at_ms,
        )
    except WebhookAuthError as exc:
        logger.warning("Upstox webhook rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    if payload.message_type != "access_token":
        logger.warning("Upstox token callback received invalid message_type: %s", payload.message_type)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid message_type: {payload.message_type}",
        )

    try:
        expires_at_ms = int(payload.expires_at)
    except (ValueError, TypeError) as exc:
        logger.exception("Upstox token callback received malformed expires_at timestamp")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid expires_at timestamp: {exc}",
        ) from exc

    try:
        success = token_manager.upgrade_from_webhook(
            access_token=payload.access_token,
            expires_at_ms=expires_at_ms,
        )
    except Exception as exc:
        logger.exception("Failed to apply webhook token upgrade inside TokenManager")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    if success:
        logger.info("Upstox access token successfully upgraded via webhook")
        return {"status": "success", "detail": "token_upgraded"}
    logger.debug("Upstox token upgrade via webhook skipped (token is older than current)")
    return {"status": "skipped", "detail": "token_is_stale"}