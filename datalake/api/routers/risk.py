"""Risk management endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from datalake.api.deps import get_risk_manager
from datalake.api.auth import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/state", response_model=dict)
async def get_risk_state(risk_manager=Depends(get_risk_manager)):
    """Get current risk management state.
    
    Returns kill switch status, daily PnL, and risk limits.
    """
    return {
        "kill_switch_active": risk_manager._config.kill_switch,
        "daily_pnl": float(risk_manager._daily_pnl),
        "daily_loss_limit_pct": float(risk_manager._config.max_daily_loss_pct),
        "max_position_pct": float(risk_manager._config.max_position_pct),
        "max_gross_exposure_pct": float(risk_manager._config.max_gross_exposure_pct),
    }


@router.post("/kill-switch", response_model=dict)
async def toggle_kill_switch(risk_manager: RiskManager = Depends(get_risk_manager)):
    """Toggle the kill switch.
    
    When active, all orders will be rejected by the risk manager.
    """
    risk_manager.set_kill_switch(not risk_manager._config.kill_switch)
    return {
        "status": "success",
        "kill_switch_active": risk_manager._config.kill_switch,
    }
