"""News endpoint — fetches market/instrument news from broker."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.auth import require_auth
from api.deps import get_broker_service

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("")
async def get_news(
    symbol: str | None = Query(None, description="Filter by symbol"),
    category: str | None = Query(None, description="Filter by category"),
    limit: int = Query(20, ge=1, le=100),
):
    """Fetch market or instrument news from the active broker.

    Requires a broker with news support (currently Upstox only).
    """
    broker_service = get_broker_service()
    if broker_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Broker service not available",
        )

    gateway = getattr(broker_service, "active_broker", None)
    if gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No active broker connection",
        )

    news_adapter = getattr(gateway, "news", None)
    if news_adapter is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="News not supported by current broker",
        )

    try:
        raw_items = news_adapter.get_news(
            symbol=symbol,
            category=category or "holdings",
        )

        items = []
        for item in raw_items[:limit]:
            items.append({
                "headline": item.get("headline", ""),
                "summary": item.get("summary", ""),
                "symbol": item.get("symbol", ""),
                "category": item.get("category", ""),
                "source": item.get("source", ""),
                "timestamp": item.get("timestamp", ""),
                "url": item.get("url"),
            })

        return {"items": items, "count": len(items)}

    except Exception as exc:
        logger.error("News fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"News fetch failed: {exc!s}",
        ) from exc
