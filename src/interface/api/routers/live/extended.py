"""Extended broker features on live REST surface (capability-gated).

All order-modifying endpoints route through ExtendedOrderService for
risk checks and event publishing. Read-only endpoints call broker directly.
"""

from __future__ import annotations

import logging
import warnings
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status

from domain.capabilities.broker_capabilities import BrokerCapabilities
from domain.ports.broker_id import BrokerId
from interface.api.auth import require_admin, require_auth
from interface.api.deps import (
    get_broker_service,
    get_event_bus,
    get_live_broker_name,
    get_risk_manager,
    require_live_broker,
)
from interface.api.routers.live.headers import apply_live_headers
from interface.api.routers.live.serialize import serialize_value

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


def _broker_name() -> str:
    svc = get_broker_service()
    return str(getattr(svc, "active_broker_name", "unknown") if svc else "unknown")


def _broker_id() -> BrokerId:
    return BrokerId.from_str(_broker_name())


def _broker_capabilities() -> BrokerCapabilities | None:
    """Return BrokerCapabilities for the active broker, or None if unavailable."""
    svc = get_broker_service()
    if svc is None:
        return None
    infra = getattr(svc, "broker_infrastructure", None)
    if infra is None:
        return None
    caps_fn = getattr(infra, "capabilities_for", None)
    if caps_fn is None:
        return None
    try:
        return caps_fn(_broker_name())
    except Exception:
        return None


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
    # G1: capability-driven dispatch — use ExtensionRegistry when available
    caps = _broker_capabilities()
    if caps is not None and caps.supports("margin_calculation"):
        registry = _get_extension_registry()
        if registry is not None:
            ext = registry.get("margin")
            if ext is not None:
                return serialize_value(ext.calculate(payload))
    broker_id = _broker_id()
    if broker_id == BrokerId.DHAN:
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
    caps = _broker_capabilities()
    # G1: capability-driven dispatch — prefer ExtensionRegistry
    if caps is not None and caps.supports("ledger"):
        registry = _get_extension_registry()
        if registry is not None:
            ledger = registry.get("ledger")
            if ledger is not None:
                return serialize_value(ledger.get_ledger(from_date, to_date))
    broker_id = _broker_id()
    if broker_id == BrokerId.DHAN:
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
    caps = _broker_capabilities()
    # G1: capability-driven dispatch — prefer ExtensionRegistry
    if caps is not None and caps.supports("static_ip"):
        registry = _get_extension_registry()
        if registry is not None:
            ext = registry.get("static_ip")
            if ext is not None:
                return serialize_value(ext.get_static_ip())
    broker_id = _broker_id()
    if broker_id == BrokerId.DHAN:
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
    caps = _broker_capabilities()
    # G1: capability-driven dispatch — prefer ExtensionRegistry
    if caps is not None and caps.supports("static_ip"):
        registry = _get_extension_registry()
        if registry is not None:
            ext = registry.get("static_ip")
            if ext is not None:
                return serialize_value(ext.set_static_ip(payload))
    broker_id = _broker_id()
    if broker_id == BrokerId.DHAN:
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


@router.post("/kill-switch", dependencies=[Depends(require_admin)])
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
    # G1: capability-driven dispatch — use BrokerCapabilities
    caps = _broker_capabilities()
    if caps is not None and caps.supports("ipo"):
        apply_live_headers(response, get_live_broker_name())
        return serialize_value(_extended(gw).get_ipos(status=status))
    _require_broker("upstox")
    apply_live_headers(response, get_live_broker_name())
    return serialize_value(_extended(gw).get_ipos(status=status))


@router.get("/mutual-funds")
async def live_mf_holdings(
    response: Response = None, gw: Any = Depends(require_live_broker)
) -> Any:
    # G1: capability-driven dispatch
    caps = _broker_capabilities()
    if caps is not None and caps.supports("mutual_funds"):
        apply_live_headers(response, get_live_broker_name())
        return serialize_value(_extended(gw).get_mutual_fund_holdings())
    _require_broker("upstox")
    apply_live_headers(response, get_live_broker_name())
    return serialize_value(_extended(gw).get_mutual_fund_holdings())


@router.post("/mutual-funds")
async def live_mf_order(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    # G1: capability-driven dispatch
    caps = _broker_capabilities()
    if caps is not None and caps.supports("mutual_funds"):
        apply_live_headers(response, get_live_broker_name())
        return serialize_value(_extended(gw).place_mutual_fund_order(payload))
    _require_broker("upstox")
    apply_live_headers(response, get_live_broker_name())
    return serialize_value(_extended(gw).place_mutual_fund_order(payload))


@router.post("/payments/payout")
async def live_payout(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    # G1: capability-driven dispatch
    caps = _broker_capabilities()
    if caps is not None and caps.supports("payout"):
        apply_live_headers(response, get_live_broker_name())
        return serialize_value(_extended(gw).initiate_payout(payload))
    _require_broker("upstox")
    apply_live_headers(response, get_live_broker_name())
    return serialize_value(_extended(gw).initiate_payout(payload))


@router.get("/fundamentals/{isin}")
async def live_fundamentals(
    isin: str,
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    # G1: capability-driven dispatch
    caps = _broker_capabilities()
    if caps is not None and caps.supports("fundamentals"):
        apply_live_headers(response, get_live_broker_name())
        return serialize_value(_extended(gw).get_pnl(isin))
    _require_broker("upstox")
    apply_live_headers(response, get_live_broker_name())
    return serialize_value(_extended(gw).get_pnl(isin))
