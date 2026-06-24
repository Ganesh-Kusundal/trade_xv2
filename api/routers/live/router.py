"""Aggregate live broker router."""

from __future__ import annotations

from fastapi import APIRouter

from api.routers.live import derivatives, extended, health, market, orders, portfolio

router = APIRouter(tags=["Live Broker"])
router.include_router(health.router)
router.include_router(market.router)
router.include_router(portfolio.router)
router.include_router(orders.router)
router.include_router(derivatives.router)
router.include_router(extended.router)
