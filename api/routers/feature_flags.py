"""Feature flag management endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.auth import require_auth
from config.feature_flags import FeatureFlags

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


class FlagToggleResponse(BaseModel):
    """Response for flag toggle operation."""

    name: str
    enabled: bool
    message: str


class RolloutUpdateRequest(BaseModel):
    """Request to update rollout percentage."""

    percentage: int = Field(..., ge=0, le=100, description="Rollout percentage (0-100)")


class RolloutUpdateResponse(BaseModel):
    """Response for rollout update operation."""

    name: str
    rollout_percentage: int
    message: str


class FlagInfoResponse(BaseModel):
    """Response for flag info."""

    name: str
    enabled: bool
    rollout_percentage: int
    description: str
    default: bool


class AllFlagsResponse(BaseModel):
    """Response for all flags."""

    flags: dict[str, FlagInfoResponse]
    count: int


@router.get("", response_model=AllFlagsResponse, summary="List all feature flags")
async def list_flags():
    """List all feature flags with their current state and configuration."""
    flags = FeatureFlags.get_all_flags()
    flag_responses = {
        name: FlagInfoResponse(**info)
        for name, info in flags.items()
    }
    return AllFlagsResponse(flags=flag_responses, count=len(flag_responses))


@router.get("/{name}", response_model=FlagInfoResponse, summary="Get flag info")
async def get_flag(name: str):
    """Get detailed information about a specific feature flag.

    Args:
        name: Flag name (e.g., "SMART_ROUTING").
    """
    info = FeatureFlags.get_flag_info(name)
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{name}' not found",
        )
    return FlagInfoResponse(**info)


@router.post("/{name}/toggle", response_model=FlagToggleResponse, summary="Toggle flag")
async def toggle_flag(name: str):
    """Toggle a feature flag on/off (admin only).

    Args:
        name: Flag name (e.g., "SMART_ROUTING").
    """
    info = FeatureFlags.get_flag_info(name)
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{name}' not found",
        )

    current_state = info["enabled"]
    new_state = not current_state
    FeatureFlags.set_flag(name, new_state)

    return FlagToggleResponse(
        name=name,
        enabled=new_state,
        message=f"Flag '{name}' {'enabled' if new_state else 'disabled'}",
    )


@router.post("/{name}/rollout", response_model=RolloutUpdateResponse, summary="Set rollout percentage")
async def set_rollout(name: str, body: RolloutUpdateRequest):
    """Set the rollout percentage for a feature flag (admin only).

    Args:
        name: Flag name (e.g., "SMART_ROUTING").
        body: Request body with percentage (0-100).
    """
    info = FeatureFlags.get_flag_info(name)
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature flag '{name}' not found",
        )

    FeatureFlags.set_rollout_percentage(name, body.percentage)

    return RolloutUpdateResponse(
        name=name,
        rollout_percentage=body.percentage,
        message=f"Rollout for '{name}' set to {body.percentage}%",
    )
