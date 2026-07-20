"""Risk management endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from interface.api.auth import require_admin, require_auth
from interface.api.deps import get_risk_manager
from application.oms._internal.risk_manager import RiskManager

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/state", response_model=dict)
async def get_risk_state(risk_manager: RiskManager = Depends(get_risk_manager)) -> dict:
    """Get current risk management state.

    Returns kill switch status, daily PnL, and risk limits.
    """
    return risk_manager.snapshot()


@router.post(
    "/kill-switch",
    response_model=dict,
    dependencies=[Depends(require_admin)],
)
async def toggle_kill_switch(risk_manager: RiskManager = Depends(get_risk_manager)) -> dict:
    """Toggle the kill switch.

    When active, all orders will be rejected by the risk manager.
    """
    risk_manager.set_kill_switch(not risk_manager.kill_switch)
    return {
        "status": "success",
        "kill_switch_active": risk_manager.kill_switch,
    }
