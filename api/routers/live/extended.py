"""Extended broker features on live REST surface (capability-gated).

All order-modifying endpoints route through ExtendedOrderService for
risk checks and event publishing. Read-only endpoints call broker directly.
"""

from __future__ import annotations

import logging
import warnings
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status

from api.auth import require_auth
from api.deps import (
    get_broker_service,
    get_event_bus,
    get_live_broker_name,
    get_risk_manager,
    require_live_broker,
)
from api.routers.live.headers import apply_live_headers
from api.routers.live.serialize import serialize_value

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


def _broker_name() -> str:
    svc = get_broker_service()
    return str(getattr(svc, "active_broker_name", "unknown") if svc else "unknown")


def _require_broker(expected: str) -> None:
    if _broker_name() != expected:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Feature not supported on broker {_broker_name()}",
        )


def _get_extension_registry() -> Any | None:
    """Return ExtensionRegistry from broker infrastructure (or None)."""
    svc = get_broker_service()
    infra = getattr(svc, "broker_infrastructure", None) if svc else None
    if infra is not None:
        return getattr(infra, "extensions", None)
    return None


def _extended(gw: Any) -> Any:
    """Resolve extended capabilities from gateway.

    Emits a deprecation warning — callers should migrate to
    ExtensionRegistry-backed extension protocols.
    """
    warnings.warn(
        "_extended() getattr probing is deprecated — use ExtensionRegistry instead",
        DeprecationWarning,
        stacklevel=2,
    )
    ext = getattr(gw, "extended", None)
    if ext is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Extended capabilities not available on this gateway",
        )
    return ext


def _get_extended_order_service() -> Any:
    """Get or create ExtendedOrderService with OMS components."""
    from application.oms.extended_order_service import ExtendedOrderService

    return ExtendedOrderService(
        risk_manager=get_risk_manager(),
        event_bus=get_event_bus(),
        broker_service=get_broker_service(),
        extension_registry=_get_extension_registry(),
    )


@router.get("/profile")
async def live_profile(response: Response = None, gw: Any = Depends(require_live_broker)) -> Any:
    apply_live_headers(response, get_live_broker_name())
    return serialize_value(_extended(gw).get_user_profile())


@router.post("/orders/super")
async def live_super_order(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    apply_live_headers(response, get_live_broker_name())
    svc = _get_extended_order_service()
    result = svc.place_super_order(gw, payload)
    if not result.success:
        if result.risk_rejected:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=result.error)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=result.error)
    return serialize_value(result.response)


@router.post("/orders/forever")
async def live_forever_order(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    apply_live_headers(response, get_live_broker_name())
    svc = _get_extended_order_service()
    result = svc.place_forever_order(gw, payload)
    if not result.success:
        if result.risk_rejected:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=result.error)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=result.error)
    return serialize_value(result.response)


@router.post("/alerts/trigger")
async def live_trigger(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    apply_live_headers(response, get_live_broker_name())
    svc = _get_extended_order_service()
    result = svc.place_trigger(gw, payload)
    if not result.success:
        if result.risk_rejected:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=result.error)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=result.error)
    return serialize_value(result.response)


@router.post("/margin/calculate")
async def live_margin(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    apply_live_headers(response, get_live_broker_name())
    if _broker_name() == "dhan":
        warnings.warn(
            "getattr(gw, '_conn') probing is deprecated — use ExtensionRegistry instead",
            DeprecationWarning,
            stacklevel=2,
        )
        conn = getattr(gw, "_conn", None)
        if conn is None:
            raise HTTPException(
                status.HTTP_501_NOT_IMPLEMENTED, detail="Dhan connection unavailable"
            )
        margin = getattr(conn, "margin", None)
        if margin is None:
            raise HTTPException(
                status.HTTP_501_NOT_IMPLEMENTED, detail="Margin service unavailable"
            )
        return serialize_value(margin.calculate(payload))
    warnings.warn(
        "getattr(gw, '_broker') probing is deprecated — use ExtensionRegistry instead",
        DeprecationWarning,
        stacklevel=2,
    )
    broker = getattr(gw, "_broker", None)
    margin_svc = getattr(broker, "margin", None) if broker else None
    if margin_svc is not None:
        return serialize_value(margin_svc.calculate_margin(payload))
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Margin not supported")


@router.post("/orders/exit-all")
async def live_exit_all(response: Response = None, gw: Any = Depends(require_live_broker)) -> Any:
    apply_live_headers(response, get_live_broker_name())
    svc = _get_extended_order_service()
    result = svc.exit_all(gw)
    if not result.success:
        if result.risk_rejected:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=result.error)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=result.error)
    return serialize_value(result.response)


@router.get("/ledger")
async def live_ledger(
    from_date: str = Query(...),
    to_date: str = Query(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    apply_live_headers(response, get_live_broker_name())
    ext = _extended(gw)
    if _broker_name() == "dhan":
        return serialize_value(ext.get_ledger(from_date, to_date))
    warnings.warn(
        "getattr(gw, '_broker') probing is deprecated — use ExtensionRegistry instead",
        DeprecationWarning,
        stacklevel=2,
    )
    broker = getattr(gw, "_broker", None)
    portfolio = getattr(broker, "portfolio", None) if broker else None
    if portfolio is not None:
        return serialize_value(portfolio.get_ledger(from_date, to_date))
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Ledger not supported")


@router.post("/edis/authorize")
async def live_edis(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    _require_broker("dhan")
    apply_live_headers(response, get_live_broker_name())
    return serialize_value(
        _extended(gw).authorize_edis(
            payload.get("isin", ""),
            int(payload.get("quantity", 0)),
            payload.get("exchange", "NSE"),
        )
    )


@router.get("/ip")
async def live_get_ip(response: Response = None, gw: Any = Depends(require_live_broker)) -> Any:
    apply_live_headers(response, get_live_broker_name())
    if _broker_name() == "dhan":
        return serialize_value(_extended(gw).get_ip())
    warnings.warn(
        "getattr(gw, '_broker') probing is deprecated — use ExtensionRegistry instead",
        DeprecationWarning,
        stacklevel=2,
    )
    broker = getattr(gw, "_broker", None)
    static_ip = getattr(broker, "static_ip", None) if broker else None
    if static_ip is not None:
        return serialize_value(static_ip.get_static_ip())
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="IP management not supported")


@router.post("/ip")
async def live_set_ip(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    apply_live_headers(response, get_live_broker_name())
    if _broker_name() == "dhan":
        return serialize_value(
            _extended(gw).set_ip(payload.get("ip", ""), payload.get("type", "static"))
        )
    warnings.warn(
        "getattr(gw, '_broker') probing is deprecated — use ExtensionRegistry instead",
        DeprecationWarning,
        stacklevel=2,
    )
    broker = getattr(gw, "_broker", None)
    static_ip = getattr(broker, "static_ip", None) if broker else None
    if static_ip is not None:
        return serialize_value(static_ip.set_static_ip(payload))
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="IP management not supported")


@router.post("/orders/gtt")
async def live_gtt(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    apply_live_headers(response, get_live_broker_name())
    svc = _get_extended_order_service()
    result = svc.place_gtt(gw, payload)
    if not result.success:
        if result.risk_rejected:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=result.error)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=result.error)
    return serialize_value(result.response)


@router.post("/orders/cover")
async def live_cover(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    apply_live_headers(response, get_live_broker_name())
    svc = _get_extended_order_service()
    result = svc.place_cover_order(gw, payload)
    if not result.success:
        if result.risk_rejected:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=result.error)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=result.error)
    return serialize_value(result.response)


@router.post("/orders/slice")
async def live_slice(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    apply_live_headers(response, get_live_broker_name())
    svc = _get_extended_order_service()
    result = svc.place_slice_order(gw, payload)
    if not result.success:
        if result.risk_rejected:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=result.error)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=result.error)
    return serialize_value(result.response)


@router.post("/kill-switch")
async def live_broker_kill_switch(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    apply_live_headers(response, get_live_broker_name())
    svc = _get_extended_order_service()
    result = svc.set_kill_switch(gw, payload)
    if not result.success:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=result.error)
    return serialize_value(result.response)


@router.get("/ipo")
async def live_ipo(
    status: str = Query("open"),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    _require_broker("upstox")
    apply_live_headers(response, get_live_broker_name())
    return serialize_value(_extended(gw).get_ipos(status=status))


@router.get("/mutual-funds")
async def live_mf_holdings(
    response: Response = None, gw: Any = Depends(require_live_broker)
) -> Any:
    _require_broker("upstox")
    apply_live_headers(response, get_live_broker_name())
    return serialize_value(_extended(gw).get_mutual_fund_holdings())


@router.post("/mutual-funds")
async def live_mf_order(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    _require_broker("upstox")
    apply_live_headers(response, get_live_broker_name())
    return serialize_value(_extended(gw).place_mutual_fund_order(payload))


@router.post("/payments/payout")
async def live_payout(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    _require_broker("upstox")
    apply_live_headers(response, get_live_broker_name())
    return serialize_value(_extended(gw).initiate_payout(payload))


@router.get("/fundamentals/{isin}")
async def live_fundamentals(
    isin: str,
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    _require_broker("upstox")
    apply_live_headers(response, get_live_broker_name())
    return serialize_value(_extended(gw).get_pnl(isin))
