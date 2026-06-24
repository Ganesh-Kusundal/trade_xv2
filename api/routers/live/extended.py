"""Extended broker features on live REST surface (capability-gated)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status

from api.auth import require_auth
from api.deps import get_live_broker_name, get_broker_service, require_live_broker
from api.routers.live.headers import apply_live_headers
from api.routers.live.serialize import serialize_value

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


def _extended(gw: Any) -> Any:
    ext = getattr(gw, "extended", None)
    if ext is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Extended capabilities not available on this gateway",
        )
    return ext


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
    _require_broker("dhan")
    apply_live_headers(response, get_live_broker_name())
    return serialize_value(_extended(gw).place_super_order(**payload))


@router.post("/orders/forever")
async def live_forever_order(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    apply_live_headers(response, get_live_broker_name())
    ext = _extended(gw)
    if _broker_name() == "dhan":
        return serialize_value(ext.place_forever_order(payload))
    if _broker_name() == "upstox":
        broker = getattr(gw, "_broker", None)
        if broker is None:
            raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Upstox broker unavailable")
        return serialize_value(broker.gtt.place_forever_order(payload))
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Forever orders not supported")


@router.post("/alerts/trigger")
async def live_trigger(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    apply_live_headers(response, get_live_broker_name())
    ext = _extended(gw)
    if _broker_name() == "dhan":
        return serialize_value(ext.place_conditional_trigger(payload))
    broker = getattr(gw, "_broker", None)
    if broker is not None and hasattr(broker, "alert"):
        return serialize_value(broker.alert.place_alert(payload))
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Triggers not supported")


@router.post("/margin/calculate")
async def live_margin(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    apply_live_headers(response, get_live_broker_name())
    if _broker_name() == "dhan":
        conn = getattr(gw, "_conn", None)
        if conn is None:
            raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Dhan connection unavailable")
        return serialize_value(conn.margin.calculate(payload))
    broker = getattr(gw, "_broker", None)
    if broker is not None:
        return serialize_value(broker.margin.calculate_margin(payload))
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Margin not supported")


@router.post("/orders/exit-all")
async def live_exit_all(response: Response = None, gw: Any = Depends(require_live_broker)) -> Any:
    apply_live_headers(response, get_live_broker_name())
    ext = _extended(gw)
    if hasattr(ext, "exit_all"):
        return serialize_value(ext.exit_all())
    broker = getattr(gw, "_broker", None)
    if broker is not None:
        return serialize_value(broker.exit_all.exit_all())
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="exit_all not supported")


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
    broker = getattr(gw, "_broker", None)
    if broker is not None:
        return serialize_value(broker.portfolio.get_ledger(from_date, to_date))
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
    broker = getattr(gw, "_broker", None)
    if broker is not None:
        return serialize_value(broker.static_ip.get_static_ip())
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="IP management not supported")


@router.post("/ip")
async def live_set_ip(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    apply_live_headers(response, get_live_broker_name())
    if _broker_name() == "dhan":
        return serialize_value(_extended(gw).set_ip(payload.get("ip", ""), payload.get("type", "static")))
    broker = getattr(gw, "_broker", None)
    if broker is not None:
        return serialize_value(broker.static_ip.set_static_ip(payload))
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="IP management not supported")


@router.post("/orders/gtt")
async def live_gtt(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    _require_broker("upstox")
    apply_live_headers(response, get_live_broker_name())
    broker = getattr(gw, "_broker", None)
    if broker is None:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Upstox broker unavailable")
    return serialize_value(broker.gtt.place_gtt_single(payload))


@router.post("/orders/cover")
async def live_cover(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    _require_broker("upstox")
    apply_live_headers(response, get_live_broker_name())
    broker = getattr(gw, "_broker", None)
    if broker is None:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Upstox broker unavailable")
    from decimal import Decimal
    from domain import OrderRequest, OrderType, ProductType, Side, Validity

    req = OrderRequest(
        symbol=payload.get("symbol", ""),
        exchange=payload.get("exchange", "NSE"),
        side=Side(payload.get("side", "BUY")),
        quantity=int(payload.get("quantity", 0)),
        order_type=OrderType(payload.get("order_type", "MARKET")),
        product_type=ProductType(payload.get("product_type", "INTRADAY")),
        validity=Validity(payload.get("validity", "DAY")),
        price=Decimal(str(payload.get("price", "0"))),
    )
    return serialize_value(
        broker.cover.place_cover_order(req, Decimal(str(payload.get("stop_loss_price", "0"))))
    )


@router.post("/orders/slice")
async def live_slice(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    apply_live_headers(response, get_live_broker_name())
    if _broker_name() == "dhan":
        conn = getattr(gw, "_conn", None)
        if conn is not None:
            return serialize_value(conn.orders.place_slice_order(**payload))
    broker = getattr(gw, "_broker", None)
    if broker is not None:
        from domain.requests import SliceOrderRequest

        req = SliceOrderRequest(**payload)
        return serialize_value(broker.slice.place_slice_order(req))
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Slice orders not supported")


@router.post("/kill-switch")
async def live_broker_kill_switch(
    payload: dict[str, Any] = Body(...),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> Any:
    _require_broker("upstox")
    apply_live_headers(response, get_live_broker_name())
    broker = getattr(gw, "_broker", None)
    if broker is None:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Upstox broker unavailable")
    updates = payload.get("updates", [])
    return serialize_value(broker.kill_switch.set_status(updates))


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
async def live_mf_holdings(response: Response = None, gw: Any = Depends(require_live_broker)) -> Any:
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
