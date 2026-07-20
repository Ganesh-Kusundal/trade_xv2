"""Extended broker feature CLI commands (capability-gated)."""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

from rich.console import Console

from domain.ports.broker_id import BrokerId
from interface.ui.commands.registry import CommandResult
from interface.ui.services.broker_service import BrokerService

logger = logging.getLogger(__name__)


def _gateway(broker_service: BrokerService) -> Any:
    return broker_service.active_broker


def _broker_name(broker_service: BrokerService) -> str:
    return broker_service.active_broker_name


def _extended(gw: Any) -> Any:
    ext = getattr(gw, "extended", None)
    if ext is None:
        raise RuntimeError("Extended capabilities not available on this gateway")
    return ext


def _ok(console: Console, label: str, data: Any) -> CommandResult:
    console.print(f"[green]✅ {label}[/green]")
    return CommandResult(success=True, data={"result": data})


def _fail(console: Console, exc: Exception) -> CommandResult:
    logger.exception("Extended command failed")
    console.print(f"[red]❌ {exc}[/red]")
    return CommandResult(success=False, error=str(exc))


def _bid(broker_service: BrokerService) -> BrokerId | None:
    try:
        return BrokerId.from_str(_broker_name(broker_service))
    except ValueError:
        return None


def _caps(broker_service: BrokerService) -> Any:
    gw = _gateway(broker_service)
    try:
        return gw.capabilities()
    except (AttributeError, TypeError):
        return None


def super_order(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    # G1: capability-driven dispatch
    caps = _caps(broker_service)
    if caps is None or not caps.supports_super_order:
        return CommandResult(success=False, error="super-order is not supported on this broker")
    try:
        payload = json.loads(" ".join(args)) if args else {}
        result = _extended(_gateway(broker_service)).place_super_order(**payload)
        return _ok(console, "Super order placed", result)
    except Exception as exc:
        return _fail(console, exc)


def forever_order(
    args: list[str], broker_service: BrokerService, console: Console
) -> CommandResult:
    try:
        payload = json.loads(" ".join(args)) if args else {}
        gw = _gateway(broker_service)
        # G1: capability-driven dispatch
        bid = _bid(broker_service)
        if bid == BrokerId.DHAN:
            result = _extended(gw).place_forever_order(payload)
        elif bid == BrokerId.UPSTOX:
            result = gw._broker.gtt.place_forever_order(payload)
        else:
            return CommandResult(success=False, error="forever-order not supported on this broker")
        return _ok(console, "Forever order placed", result)
    except Exception as exc:
        return _fail(console, exc)


def trigger(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    try:
        payload = json.loads(" ".join(args)) if args else {}
        gw = _gateway(broker_service)
        # G1: capability-driven dispatch
        bid = _bid(broker_service)
        if bid == BrokerId.DHAN:
            result = _extended(gw).place_conditional_trigger(payload)
        else:
            result = gw._broker.alert.place_alert(payload)
        return _ok(console, "Trigger placed", result)
    except Exception as exc:
        return _fail(console, exc)


def margin(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    try:
        payload = json.loads(" ".join(args)) if args else {}
        gw = _gateway(broker_service)
        # G1: capability-driven dispatch
        bid = _bid(broker_service)
        if bid == BrokerId.DHAN:
            result = gw._conn.margin.calculate(payload)
        else:
            result = gw._broker.margin.calculate_margin(payload)
        return _ok(console, "Margin calculated", result)
    except Exception as exc:
        return _fail(console, exc)


def exit_all(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    try:
        gw = _gateway(broker_service)
        ext = getattr(gw, "extended", None)
        if ext is not None and hasattr(ext, "exit_all"):
            result = ext.exit_all()
        else:
            result = gw._broker.exit_all.exit_all()
        return _ok(console, "Exit-all submitted", result)
    except Exception as exc:
        return _fail(console, exc)


def ledger(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    if len(args) < 2:
        return CommandResult(success=False, error="Usage: ledger <from_date> <to_date>")
    try:
        gw = _gateway(broker_service)
        # G1: capability-driven dispatch
        bid = _bid(broker_service)
        if bid == BrokerId.DHAN:
            result = _extended(gw).get_ledger(args[0], args[1])
        else:
            result = gw._broker.portfolio.get_ledger(args[0], args[1])
        return _ok(console, "Ledger fetched", result)
    except Exception as exc:
        return _fail(console, exc)


def edis(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    # G1: capability-driven dispatch
    bid = _bid(broker_service)
    if bid != BrokerId.DHAN:
        return CommandResult(success=False, error="edis is Dhan-only")
    try:
        payload = json.loads(" ".join(args)) if args else {}
        result = _extended(_gateway(broker_service)).authorize_edis(
            payload.get("isin", ""),
            int(payload.get("quantity", 0)),
            payload.get("exchange", "NSE"),
        )
        return _ok(console, "EDIS authorized", result)
    except Exception as exc:
        return _fail(console, exc)


def ip(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    try:
        gw = _gateway(broker_service)
        # G1: capability-driven dispatch
        bid = _bid(broker_service)
        if not args:
            if bid == BrokerId.DHAN:
                result = _extended(gw).get_ip()
            else:
                result = gw._broker.static_ip.get_static_ip()
            return _ok(console, "IP list", result)
        payload = json.loads(" ".join(args))
        if bid == BrokerId.DHAN:
            result = _extended(gw).set_ip(payload.get("ip", ""), payload.get("type", "static"))
        else:
            result = gw._broker.static_ip.set_static_ip(payload)
        return _ok(console, "IP updated", result)
    except Exception as exc:
        return _fail(console, exc)


def profile(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    try:
        result = _extended(_gateway(broker_service)).get_user_profile()
        return _ok(console, "Profile fetched", result)
    except Exception as exc:
        return _fail(console, exc)


def gtt_order(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    # G1: capability-driven dispatch
    bid = _bid(broker_service)
    if bid != BrokerId.UPSTOX:
        return CommandResult(success=False, error="gtt-order is Upstox-only")
    try:
        payload = json.loads(" ".join(args)) if args else {}
        result = _gateway(broker_service)._broker.gtt.place_gtt_single(payload)
        return _ok(console, "GTT order placed", result)
    except Exception as exc:
        return _fail(console, exc)


def cover_order(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    # G1: capability-driven dispatch
    bid = _bid(broker_service)
    if bid != BrokerId.UPSTOX:
        return CommandResult(success=False, error="cover-order is Upstox-only")
    try:
        from domain import OrderRequest, OrderType, ProductType, Side, Validity

        payload = json.loads(" ".join(args)) if args else {}
        gw = _gateway(broker_service)
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
        result = gw._broker.cover.place_cover_order(
            req, Decimal(str(payload.get("stop_loss_price", "0")))
        )
        return _ok(console, "Cover order placed", result)
    except Exception as exc:
        return _fail(console, exc)


def slice_order(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    try:
        payload = json.loads(" ".join(args)) if args else {}
        gw = _gateway(broker_service)
        # G1: capability-driven dispatch
        bid = _bid(broker_service)
        if bid == BrokerId.DHAN:
            result = gw._conn.orders.place_slice_order(**payload)
        else:
            from domain.orders.requests import SliceOrderRequest

            result = gw._broker.slice.place_slice_order(SliceOrderRequest(**payload))
        return _ok(console, "Slice order placed", result)
    except Exception as exc:
        return _fail(console, exc)


def broker_kill_switch(
    args: list[str], broker_service: BrokerService, console: Console
) -> CommandResult:
    # G1: capability-driven dispatch
    bid = _bid(broker_service)
    if bid != BrokerId.UPSTOX:
        return CommandResult(success=False, error="broker-kill-switch is Upstox-only")
    try:
        payload = json.loads(" ".join(args)) if args else {"updates": []}
        result = _gateway(broker_service)._broker.kill_switch.set_status(payload.get("updates", []))
        return _ok(console, "Broker kill switch updated", result)
    except Exception as exc:
        return _fail(console, exc)


def ipo(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    # G1: capability-driven dispatch
    bid = _bid(broker_service)
    if bid != BrokerId.UPSTOX:
        return CommandResult(success=False, error="ipo is Upstox-only")
    try:
        status = args[0] if args else "open"
        result = _extended(_gateway(broker_service)).get_ipos(status=status)
        return _ok(console, "IPO list fetched", result)
    except Exception as exc:
        return _fail(console, exc)


def mf(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    # G1: capability-driven dispatch
    bid = _bid(broker_service)
    if bid != BrokerId.UPSTOX:
        return CommandResult(success=False, error="mf is Upstox-only")
    try:
        gw = _gateway(broker_service)
        if not args:
            result = _extended(gw).get_mutual_fund_holdings()
        else:
            payload = json.loads(" ".join(args))
            result = _extended(gw).place_mutual_fund_order(payload)
        return _ok(console, "Mutual fund operation complete", result)
    except Exception as exc:
        return _fail(console, exc)


def payout(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    # G1: capability-driven dispatch
    bid = _bid(broker_service)
    if bid != BrokerId.UPSTOX:
        return CommandResult(success=False, error="payout is Upstox-only")
    try:
        payload = json.loads(" ".join(args)) if args else {}
        result = _extended(_gateway(broker_service)).initiate_payout(payload)
        return _ok(console, "Payout initiated", result)
    except Exception as exc:
        return _fail(console, exc)


def fundamentals(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    # G1: capability-driven dispatch
    caps = _caps(broker_service)
    if caps is None or not caps.supports_fundamentals:
        return CommandResult(success=False, error="fundamentals is not supported on this broker")
    if not args:
        return CommandResult(success=False, error="Usage: fundamentals <isin>")
    try:
        result = _extended(_gateway(broker_service)).get_pnl(args[0])
        return _ok(console, "Fundamentals fetched", result)
    except Exception as exc:
        return _fail(console, exc)
