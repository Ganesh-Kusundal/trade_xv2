"""broker — developer/CI/AI CLI for the Trading OS broker layer.

Thin front-end over ``brokers.services`` — same core as SDK and MCP.
"""

from __future__ import annotations

from brokers._bootstrap import ensure_repo_src

ensure_repo_src()

import json

import click

from domain.enums import BrokerId

from brokers.cli._errors import handle_cli_errors
from brokers.cli._render import present, console
from brokers.platform_ops import (
    run_benchmark,
    run_certify,
    run_diagnose,
    run_doctor,
    run_health,
    run_mapping,
    run_verify,
)
from brokers.services import (
    cancel_order,
    extensions_from_session,
    get_capabilities,
    get_depth,
    get_depth30,
    get_funds,
    get_history,
    get_holdings,
    get_news,
    get_option_chain,
    get_orders,
    get_positions,
    get_quote,
    list_forever_orders,
    list_super_orders,
    lookup_symbol,
    modify_order,
    place_order,
    probe_depth_ws,
    run_connect,
    run_market_hours,
    run_subscribe_probe,
    status_from_session,
)
from brokers.session import BrokerSession, available_brokers


@click.group()
@click.option("--broker", default="paper", help="Broker id (paper/dhan/upstox).")
@click.option("--json", "as_json", is_flag=True, help="Emit raw JSON instead of Rich tables.")
@click.option("--yaml", "as_yaml", is_flag=True, help="Emit YAML instead of Rich tables.")
@click.option("--quiet", "-q", "quiet", is_flag=True, help="Suppress output (exit code only).")
@click.pass_context
def broker(ctx: click.Context, broker: str, as_json: bool, as_yaml: bool, quiet: bool) -> None:
    """Trading OS broker developer CLI."""
    ctx.ensure_object(dict)
    ctx.obj["broker"] = broker
    ctx.obj["json"] = as_json
    ctx.obj["yaml"] = as_yaml
    ctx.obj["quiet"] = quiet


def _bid(ctx: click.Context, broker_id: str | None = None) -> str:
    return broker_id or ctx.obj["broker"]


def _is_live_broker(broker_id: str) -> bool:
    return broker_id != BrokerId.PAPER


def _svc_kw(ctx: click.Context) -> dict:
    """Pass held shell session into service calls (avoids reopening per command)."""
    sess = ctx.obj.get("shell_session")
    return {"session": sess} if sess is not None else {}


def _session_info_from_error(broker_id: str, exc: Exception) -> dict:
    return {
        "broker_id": broker_id,
        "connected": False,
        "mode": None,
        "orders_enabled": None,
        "error": str(exc),
        "remediation": getattr(exc, "remediation", "") or "",
    }


def _close_shell_session(ctx: click.Context) -> None:
    sess = ctx.obj.pop("shell_session", None)
    if sess is not None:
        sess.close()


def _open_shell_session(ctx: click.Context, broker_id: str) -> tuple[BrokerSession | None, dict]:
    """Open one BrokerSession for the shell lifetime."""
    _close_shell_session(ctx)
    try:
        sess = BrokerSession(broker_id)
        ctx.obj["shell_session"] = sess
        return sess, status_from_session(sess)
    except Exception as exc:
        return None, _session_info_from_error(broker_id, exc)


def _reopen_shell_session(ctx: click.Context, broker_id: str) -> dict:
    """Close and reopen the held session (connect/retry only)."""
    _, info = _open_shell_session(ctx, broker_id)
    return info


def _session_extensions(ctx: click.Context, broker_id: str) -> list[str]:
    sess = ctx.obj.get("shell_session")
    if sess is not None:
        return extensions_from_session(sess)
    try:
        return list(get_capabilities(broker_id, **_svc_kw(ctx)).get("extensions") or [])
    except Exception:
        return []


def _shell_invoke(ctx: click.Context, broker_id: str, name: str, args: list[str]) -> None:
    """Re-invoke a subcommand keeping the shell's broker selection."""
    try:
        broker.main(
            ["--broker", broker_id, name, *args],
            standalone_mode=False,
            obj=ctx.obj,
        )
    except SystemExit:
        pass


@broker.command("shell")
@click.pass_context
def shell_cmd(ctx: click.Context) -> None:
    """Interactive REPL for broker commands."""
    from brokers.cli._shell_nav import (
        Back,
        EnterSection,
        Help,
        Quit,
        RECOVERY_MENU,
        RetryConnect,
        RunCommand,
        Unknown,
        arg_hint_display,
        ask_menu_line,
        build_main_menu,
        click_command_name,
        command_needs_args,
        print_unknown,
        prompt_for_args,
        render_help_for_menu,
        render_menu,
        resolve_input,
    )

    broker_id = _bid(ctx)
    _, session = _open_shell_session(ctx, broker_id)
    declared_ext = _session_extensions(ctx, broker_id) if session.get("connected") else []
    main_menu = build_main_menu(broker, broker_id, declared_extensions=declared_ext or None)
    if _is_live_broker(broker_id) and not session.get("connected"):
        while not session.get("connected"):
            render_menu(ctx, broker_id, session, RECOVERY_MENU, group=broker)
            try:
                line = ask_menu_line(broker_id, RECOVERY_MENU)
            except (EOFError, KeyboardInterrupt):
                console.print()
                _close_shell_session(ctx)
                return
            action = resolve_input(line, RECOVERY_MENU, broker)
            if isinstance(action, Quit):
                _close_shell_session(ctx)
                return
            if isinstance(action, RetryConnect):
                session = _reopen_shell_session(ctx, broker_id)
                continue
            if isinstance(action, RunCommand):
                _shell_invoke(ctx, broker_id, action.name, action.args)
                continue
            if isinstance(action, Unknown):
                print_unknown(action.token)
                continue

    menu_stack: list = []
    try:
        while True:
            current = menu_stack[-1] if menu_stack else main_menu
            render_menu(ctx, broker_id, session, current, group=broker)
            try:
                line = ask_menu_line(broker_id, current)
            except (EOFError, KeyboardInterrupt):
                console.print()
                break

            action = resolve_input(line, current, broker)
            if isinstance(action, Quit):
                break
            if isinstance(action, Back):
                if menu_stack:
                    menu_stack.pop()
                continue
            if isinstance(action, Help):
                render_help_for_menu(broker_id, current, group=broker)
                continue
            if isinstance(action, EnterSection):
                menu_stack.append(action.menu)
                continue
            if isinstance(action, RunCommand):
                if action.name == "connect":
                    session = _reopen_shell_session(ctx, broker_id)
                    declared_ext = _session_extensions(ctx, broker_id) if session.get("connected") else []
                    main_menu = build_main_menu(broker, broker_id, declared_extensions=declared_ext or None)
                    continue
                args = list(action.args)
                if not args and command_needs_args(broker, action.name):
                    extra = prompt_for_args(
                        action.name,
                        arg_hint_display(broker, action.name),
                    )
                    args.extend(extra)
                if not click_command_name(broker, action.name):
                    print_unknown(action.name)
                    continue
                _shell_invoke(
                    ctx,
                    broker_id,
                    click_command_name(broker, action.name) or action.name,
                    args,
                )
                continue
            if isinstance(action, Unknown):
                print_unknown(action.token)
                continue
    finally:
        _close_shell_session(ctx)


@broker.command()
@click.pass_context
@handle_cli_errors
def connect(ctx: click.Context) -> None:
    """Connect and report session status."""
    kw = _svc_kw(ctx)
    if kw.get("session"):
        info = run_connect(_bid(ctx), **kw)
    else:
        s = BrokerSession(_bid(ctx))
        try:
            info = status_from_session(s)
        finally:
            s.close()
    click.echo(
        f"Connected to {info['broker_id']}: mode={info.get('mode', '?')} "
        f"orders_enabled={info.get('orders_enabled', '?')}"
    )


@broker.command()
@click.pass_context
@handle_cli_errors
def discover(ctx: click.Context) -> None:
    """List registered broker plugins."""
    present(ctx, available_brokers(), title="Brokers")


@broker.command()
@click.argument("symbol")
@click.pass_context
@handle_cli_errors
def quote(ctx: click.Context, symbol: str) -> None:
    """Fetch a quote for SYMBOL."""
    present(ctx, get_quote(_bid(ctx), symbol, **_svc_kw(ctx)), title=f"Quote — {symbol}")


@broker.command()
@click.argument("symbol")
@click.option("--tf", default="1D", help="Timeframe (1m/5m/15m/1D/...).")
@click.option("--days", default=5, type=int)
@click.pass_context
@handle_cli_errors
def history(ctx: click.Context, symbol: str, tf: str, days: int) -> None:
    """Fetch history for SYMBOL."""
    series = get_history(_bid(ctx), symbol, timeframe=tf, days=days, **_svc_kw(ctx))
    present(ctx, series, title=f"History — {symbol} ({tf})")


@broker.command()
@click.argument("symbol")
@click.pass_context
@handle_cli_errors
def subscribe(ctx: click.Context, symbol: str) -> None:
    """Subscribe to live data for SYMBOL (brief check)."""
    ok = run_subscribe_probe(_bid(ctx), symbol, **_svc_kw(ctx))
    present(ctx, {"symbol": symbol, "handle": "active" if ok else "none", "subscribed": ok}, title=f"Subscribe — {symbol}")


@broker.command()
@click.argument("symbol")
@click.pass_context
@handle_cli_errors
def depth(ctx: click.Context, symbol: str) -> None:
    """Fetch market depth for SYMBOL."""
    present(ctx, get_depth(_bid(ctx), symbol, **_svc_kw(ctx)), title=f"Depth — {symbol}")


@broker.command()
@click.argument("underlying")
@click.pass_context
@handle_cli_errors
def option_chain(ctx: click.Context, underlying: str) -> None:
    """Fetch option chain for UNDERLYING."""
    present(ctx, get_option_chain(_bid(ctx), underlying, **_svc_kw(ctx)), title=f"Option chain — {underlying}")


@broker.command()
@click.pass_context
@handle_cli_errors
def positions(ctx: click.Context) -> None:
    """Show positions."""
    present(ctx, get_positions(_bid(ctx), **_svc_kw(ctx)), title="Positions")


@broker.command()
@click.pass_context
@handle_cli_errors
def holdings(ctx: click.Context) -> None:
    """Show holdings."""
    present(ctx, get_holdings(_bid(ctx), **_svc_kw(ctx)), title="Holdings")


@broker.command()
@click.pass_context
@handle_cli_errors
def funds(ctx: click.Context) -> None:
    """Show funds."""
    present(ctx, get_funds(_bid(ctx), **_svc_kw(ctx)), title="Funds")


@broker.command()
@click.pass_context
@handle_cli_errors
def orders(ctx: click.Context) -> None:
    """List orders."""
    present(ctx, get_orders(_bid(ctx), **_svc_kw(ctx)), title="Orders")


@broker.command("order")
@click.argument("symbol")
@click.argument("quantity", type=int)
@click.option("--side", default="BUY", type=click.Choice(["BUY", "SELL"], case_sensitive=False))
@click.option("--price", default=None, type=float)
@click.option("--order-type", "order_type", default="LIMIT")
@click.option("--product-type", "product_type", default="INTRADAY")
@click.pass_context
def order_cmd(
    ctx: click.Context,
    symbol: str,
    quantity: int,
    side: str,
    price: float | None,
    order_type: str,
    product_type: str,
) -> None:
    """Place an order (paper-safe by default)."""
    result = place_order(
        _bid(ctx),
        symbol,
        quantity,
        side=side,
        price=price,
        order_type=order_type,
        product_type=product_type,
        **_svc_kw(ctx),
    )
    present(ctx, result, title="Order placed")


@broker.command()
@click.argument("order_id")
@click.pass_context
def cancel(ctx: click.Context, order_id: str) -> None:
    """Cancel an order by id."""
    present(ctx, cancel_order(_bid(ctx), order_id, **_svc_kw(ctx)), title="Order cancelled")


@broker.command()
@click.argument("order_id")
@click.option("--quantity", default=None, type=int)
@click.option("--price", default=None, type=float)
@click.pass_context
def modify(ctx: click.Context, order_id: str, quantity: int | None, price: float | None) -> None:
    """Modify an open order."""
    present(
        ctx,
        modify_order(_bid(ctx), order_id, quantity=quantity, price=price, **_svc_kw(ctx)),
        title="Order modified",
    )


@broker.command()
@click.pass_context
def capability(ctx: click.Context) -> None:
    """List broker capabilities for an instrument."""
    present(ctx, get_capabilities(_bid(ctx), **_svc_kw(ctx)), title="Capabilities")


@broker.command()
@click.argument("symbol")
@click.pass_context
def symbols(ctx: click.Context, symbol: str) -> None:
    """Resolve SYMBOL to canonical instrument id."""
    present(ctx, {"symbol": symbol, "instrument_id": lookup_symbol(_bid(ctx), symbol, **_svc_kw(ctx))}, title=f"Symbol — {symbol}")


@broker.command()
@click.argument("symbol")
@click.option("--exchange", default="NSE")
@click.pass_context
def instrument(ctx: click.Context, symbol: str, exchange: str) -> None:
    """Resolve SYMBOL to public instrument metadata (no broker tokens)."""
    from brokers.services import lookup_instrument

    present(ctx, lookup_instrument(_bid(ctx), symbol, exchange=exchange, **_svc_kw(ctx)), title=f"Instrument — {symbol}")


@broker.command("security", hidden=True)
@click.argument("symbol")
@click.option("--exchange", default="NSE")
@click.pass_context
def security(ctx: click.Context, symbol: str, exchange: str) -> None:
    """Deprecated alias for ``instrument``."""
    ctx.invoke(instrument, symbol=symbol, exchange=exchange)


@broker.command()
@click.pass_context
def mappings(ctx: click.Context) -> None:
    """Run mapping round-trip validation."""
    report = run_mapping(_bid(ctx), **_svc_kw(ctx))
    report.print_report()
    if not report.all_passed:
        raise SystemExit(1)


@broker.command()
@click.pass_context
def diagnose(ctx: click.Context) -> None:
    """Run diagnostics."""
    run_diagnose(_bid(ctx)).print_report()


@broker.command()
@click.pass_context
def health(ctx: click.Context) -> None:
    """Run health checks."""
    run_health(_bid(ctx)).print_report()


@broker.command()
@click.pass_context
def doctor(ctx: click.Context) -> None:
    """Run full environment pre-flight (kubectl-style)."""
    run_doctor(_bid(ctx)).print_report()


@broker.command()
@click.pass_context
def benchmark(ctx: click.Context) -> None:
    """Run latency/throughput benchmark."""
    run_benchmark(_bid(ctx)).print_report()


@broker.command()
@click.pass_context
def market_hours(ctx: click.Context) -> None:
    """Run market-hours behavior matrix for current phase."""
    run_market_hours(_bid(ctx)).print_report()


@broker.command("depth20")
@click.argument("symbol")
@click.pass_context
def depth20_cmd(ctx: click.Context, symbol: str) -> None:
    """Fetch 20-level WS depth for SYMBOL (Dhan)."""
    present(ctx, probe_depth_ws(_bid(ctx), symbol, levels=20, **_svc_kw(ctx)), title=f"Depth20 — {symbol}")


@broker.command("depth200")
@click.argument("symbol")
@click.pass_context
def depth200_cmd(ctx: click.Context, symbol: str) -> None:
    """Fetch 200-level WS depth for SYMBOL (Dhan)."""
    present(ctx, probe_depth_ws(_bid(ctx), symbol, levels=200, **_svc_kw(ctx)), title=f"Depth200 — {symbol}")


@broker.command("depth30")
@click.argument("symbol")
@click.pass_context
def depth30_cmd(ctx: click.Context, symbol: str) -> None:
    """Fetch 30-level depth for SYMBOL (Upstox)."""
    present(ctx, get_depth30(_bid(ctx), symbol, **_svc_kw(ctx)), title=f"Depth30 — {symbol}")


@broker.command()
@click.argument("symbol", required=False)
@click.pass_context
def news(ctx: click.Context, symbol: str | None) -> None:
    """Fetch news (optional SYMBOL filter, Upstox)."""
    present(ctx, get_news(_bid(ctx), symbol=symbol, **_svc_kw(ctx)), title="News")


@broker.command("super_orders")
@click.pass_context
def super_orders_cmd(ctx: click.Context) -> None:
    """List Dhan super/bracket orders."""
    present(ctx, list_super_orders(_bid(ctx), **_svc_kw(ctx)), title="Super orders")


@broker.command("forever_orders")
@click.pass_context
def forever_orders_cmd(ctx: click.Context) -> None:
    """List Dhan forever orders."""
    present(ctx, list_forever_orders(_bid(ctx), **_svc_kw(ctx)), title="Forever orders")


@broker.command()
@click.argument("broker_id", required=False)
@click.option("--live", is_flag=True, help="Run live API tests (requires credentials).")
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def certify(ctx: click.Context, broker_id: str | None, live: bool, json_output: bool) -> None:
    """Run the full broker certification suite."""
    report = run_certify(_bid(ctx, broker_id), live=live)
    if json_output:
        click.echo(json.dumps(report.to_dict(live=live), default=str))
    else:
        report.print_report()
    if not report.is_certified:
        raise SystemExit(1)


@broker.command()
@click.argument("broker_id", required=False)
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def verify(ctx: click.Context, broker_id: str | None, json_output: bool) -> None:
    """Startup self-test: config→auth→caps→mappings→quote→history→ws→PASS."""
    report = run_verify(_bid(ctx, broker_id))
    if json_output:
        click.echo(json.dumps(report.to_dict(), default=str))
    else:
        report.print_report()
    if not report.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    broker(obj={})
