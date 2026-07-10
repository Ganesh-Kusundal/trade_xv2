"""FastAPI router for receiving Upstox webhook callbacks.

Exposes public callback endpoint for receiving daily generated access tokens.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

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
    """Resolve the active broker's token manager without importing broker packages.

    Raises:
        HTTPException: 503 if broker service or gateway is not initialized,
                       400 if the active broker is not Upstox.
    """
    if broker_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Broker service is not configured",
        )

    active_name = getattr(broker_service, "active_broker_name", None)
    if active_name != "upstox":
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

    # Resolve inner broker facade from gateway wrapper
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
    payload: UpstoxTokenWebhookPayload,
    token_manager: _WebhookTokenUpgrader = Depends(get_upstox_token_manager),
) -> dict[str, str]:
    """Public webhook callback for Upstox daily access token delivery.

    Bypasses standard X-API-Key auth since requests originate from Upstox.
    """
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
        )

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
        )

    if success:
        logger.info("Upstox access token successfully upgraded via webhook")
        return {"status": "success", "detail": "token_upgraded"}
    else:
        logger.debug("Upstox token upgrade via webhook skipped (token is older than current)")
        return {"status": "skipped", "detail": "token_is_stale"}
