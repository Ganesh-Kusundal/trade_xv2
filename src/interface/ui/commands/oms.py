"""CLI command handler for OMS, orders, and trade operations."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rich.console import Console
from rich.table import Table

from interface.ui.services.broker_service import BrokerService


def _parse_place_order_args(args: list[str]) -> dict | None:
    """Parse ``tradex oms place SYM EX SIDE QTY [PRICE] [flags...]``."""
    if not args or args[0] != "place":
        return None
    positional: list[str] = []
    flags: dict[str, str] = {}
    i = 1
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            key = a
            # If the next token is the value (no leading --), consume it.
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                flags[key] = args[i + 1]
                i += 2
                continue
            flags[key] = "true"
            i += 1
            continue
        positional.append(a)
        i += 1
    if len(positional) < 4:
        return {"_error": "Usage: tradex oms place SYMBOL EXCHANGE SIDE QUANTITY [PRICE] [--type MKT|LMT] [--product MIS|NRML|CNC]"}
    try:
        quantity = int(positional[3])
    except ValueError:
        return {"_error": f"Quantity must be an integer, got {positional[3]!r}"}
    price = None
    if len(positional) >= 5:
        try:
            price = Decimal(positional[4])
        except InvalidOperation:
            return {"_error": f"Price must be a decimal, got {positional[4]!r}"}
    return {
        "symbol": positional[0],
        "exchange": positional[1],
        "side": positional[2].upper(),
        "quantity": quantity,
        "price": price,
        "order_type": flags.get("--type", "MKT").upper(),
        "product_type": flags.get("--product", "MIS").upper(),
    }


def place_order_cmd(
    args: list[str],
    broker_service: BrokerService,
    console: Console,
) -> None:
    """Phase 6: ``tradex oms place ...`` routes through BrokerService.

    The OMS is the single chokepoint for order placement — risk check,
    idempotency, event publishing. If the runtime is not
    ``live_actionable`` (readiness gate failed, no broker credentials,
    OMS not wired) the command refuses with a clear error.
    """
    parsed = _parse_place_order_args(args)
    if parsed is None:
        console.print(
            "[yellow]Available oms subcommands:[/yellow]\n"
            "  oms place SYMBOL EXCHANGE SIDE QUANTITY [PRICE] "
            "[--type MKT|LMT] [--product MIS|NRML|CNC]\n"
            "  oms (no args — show OMS summary)\n"
            "  orders [status_filter]\n"
            "  trades"
        )
        return
    if "_error" in parsed:
        console.print(f"[red]{parsed['_error']}[/red]")
        return
    if not broker_service.live_actionable:
        console.print(
            "[red]OMS refused: runtime is not live-actionable. "
            "Run `tradex doctor` for the production readiness report; "
            "address every failing check before placing orders.[/red]"
        )
        return
    tc = broker_service.trading_context
    if tc is None:
        console.print(
            "[red]OMS refused: no TradingContext available. "
            "Verify .env.local credentials and broker connectivity.[/red]"
        )
        return
    try:
        order = broker_service.place_order(
            symbol=parsed["symbol"],
            exchange=parsed["exchange"],
            side=parsed["side"],
            quantity=parsed["quantity"],
            price=parsed["price"],
            order_type=parsed["order_type"],
        )
    except Exception as exc:
        console.print(f"[red]place_order failed: {exc}[/red]")
        return
    console.print(
        f"[green]Order accepted:[/green] {order.order_id} "
        f"{order.symbol} {order.side.value} {order.quantity} "
        f"@ {order.price} status={order.status.value}"
    )


def show_orders(
    broker_service: BrokerService, console: Console, status_filter: str | None = None
) -> None:
    """Print the orders book with optional status filtering."""
    gw = broker_service.active_broker
    try:
        orders = gw.orders.get_orderbook()

        # Apply status filter
        if status_filter:
            filt = status_filter.upper()
            if filt == "PENDING":
                orders = [o for o in orders if o.status.value in ("OPEN", "PARTIAL", "PENDING")]
            elif filt == "FILLED":
                orders = [o for o in orders if o.status.value == "COMPLETE"]
            else:
                orders = [o for o in orders if o.status.value == filt]

        title = "Today's Orders"
        if status_filter:
            title += f" (Filter: {status_filter.upper()})"

        table = Table(title=title, header_style="bold blue")
        table.add_column("Order ID", style="bold white")
        table.add_column("Symbol", style="bold white")
        table.add_column("Side", justify="center")
        table.add_column("Type", justify="center")
        table.add_column("Qty (Filled/Total)", justify="center")
        table.add_column("Limit Price", justify="right")
        table.add_column("Avg Price", justify="right")
        table.add_column("Status", justify="center")
        table.add_column("Time", justify="center")

        for o in orders:
            side_style = "green" if o.side.value == "BUY" else "red"

            # Status styling
            if o.status.value == "COMPLETE":
                status_style = "green"
            elif o.status.value in ("OPEN", "PARTIAL", "PENDING"):
                status_style = "yellow"
            elif o.status.value == "CANCELLED":
                status_style = "dim white"
            else:
                status_style = "red"

            time_str = o.order_timestamp.strftime("%H:%M:%S") if o.order_timestamp else "N/A"

            limit_price = o.price
            avg_price = o.average_price

            table.add_row(
                o.order_id or "N/A",
                o.symbol,
                f"[{side_style}]{o.side.value}[/{side_style}]",
                o.order_type.value,
                f"{o.filled_quantity}/{o.quantity}",
                f"{limit_price:,.2f}" if limit_price and limit_price > 0 else "MARKET",
                f"{avg_price:,.2f}" if avg_price and avg_price > 0 else "-",
                f"[{status_style}]{o.status.value}[/{status_style}]",
                time_str,
            )

        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error fetching orders: {exc}[/red]")


def show_trades(broker_service: BrokerService, console: Console) -> None:
    """Print the trades execution list."""
    gw = broker_service.active_broker
    try:
        trades = gw.orders.get_trade_book()
        table = Table(title="Today's Trades Execution Book", header_style="bold yellow")
        table.add_column("Trade ID", style="bold white")
        table.add_column("Order ID", style="dim white")
        table.add_column("Symbol", style="bold white")
        table.add_column("Side", justify="center")
        table.add_column("Qty", justify="right")
        table.add_column("Price", justify="right")
        table.add_column("Value", justify="right")
        table.add_column("Time", justify="center")

        for t in trades:
            side_style = "green" if t.side.value == "BUY" else "red"
            time_str = t.timestamp.strftime("%H:%M:%S") if t.timestamp else "N/A"
            trade_value = t.price * t.quantity
            table.add_row(
                t.trade_id,
                t.order_id,
                t.symbol,
                f"[{side_style}]{t.side.value}[/{side_style}]",
                str(t.quantity),
                f"{t.price:,.2f}",
                f"{trade_value:,.2f}",
                time_str,
            )

        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error fetching trades: {exc}[/red]")


def show_oms_summary(broker_service: BrokerService, console: Console) -> None:
    """Print the general OMS dashboard."""
    gw = broker_service.active_broker
    try:
        orders = gw.orders.get_orderbook()

        stats = {
            "open": 0,
            "pending": 0,
            "filled": 0,
            "rejected": 0,
            "cancelled": 0,
        }
        for o in orders:
            sv = o.status.value
            if sv == "OPEN":
                stats["open"] += 1
            elif sv in ("PENDING", "PARTIAL"):
                stats["pending"] += 1
            elif sv == "COMPLETE":
                stats["filled"] += 1
            elif sv == "REJECTED":
                stats["rejected"] += 1
            elif sv == "CANCELLED":
                stats["cancelled"] += 1

        table = Table(title="OMS Diagnostics Summary", header_style="bold cyan")
        table.add_column("Metric / Status", style="bold white")
        table.add_column("Active Count", justify="center")

        table.add_row("Open Orders (OPEN)", f"[yellow]{stats['open']}[/yellow]")
        table.add_row("Pending / Partially Filled", f"[yellow]{stats['pending']}[/yellow]")
        table.add_row("Completed Fills (COMPLETE)", f"[green]{stats['filled']}[/green]")
        table.add_row("Rejected Orders (REJECTED)", f"[red]{stats['rejected']}[/red]")
        table.add_row(
            "Cancelled Orders (CANCELLED)", f"[dim white]{stats['cancelled']}[/dim white]"
        )

        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error fetching OMS stats: {exc}[/red]")


def run(args: list[str], broker_service: BrokerService, console: Console) -> None:
    """Entry point for OMS related subcommands.

    With no arguments this prints the OMS summary. ``oms place ...``
    routes through :func:`place_order_cmd`.
    """
    if args and args[0] == "place":
        place_order_cmd(args, broker_service, console)
        return
    show_oms_summary(broker_service, console)
