"""CLI commands for advanced order composition patterns.

Implements bracket orders, OCO, basket orders, and other advanced patterns.

Commands:
    tradex bracket-order SYMBOL SIDE QTY --target PRICE --stop-loss PRICE
    tradex oco-order SYMBOL SIDE QTY --order1-price P1 --order2-price P2
    tradex basket-order --file basket.csv
"""

from __future__ import annotations

import logging
from decimal import Decimal

from rich.console import Console
from rich.table import Table

from domain import Side
from cli.commands.registry import CommandResult
from cli.services.broker_service import BrokerService
from cli.services.oms_service import OmsService

logger = logging.getLogger(__name__)


def place_bracket_order(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    """Place bracket order: entry + target + stop loss.

    Usage:
        tradex bracket-order RELIANCE BUY 10 --target 2500 --stop-loss 2400
    """
    if len(args) < 3:
        console.print("[yellow]Usage: tradex bracket-order SYMBOL SIDE QTY --target PRICE --stop-loss PRICE[/yellow]")
        return CommandResult(success=False, error="Missing required arguments: SYMBOL SIDE QTY")

    # Parse arguments
    symbol = args[0].upper()
    try:
        side = Side(args[1].upper())
    except ValueError:
        console.print(f"[red]Invalid side: {args[1]}[/red]")
        return CommandResult(success=False, error=f"Invalid side: {args[1]}")

    try:
        quantity = int(args[2])
    except ValueError:
        console.print(f"[red]Invalid quantity: {args[2]}[/red]")
        return CommandResult(success=False, error=f"Invalid quantity: {args[2]}")

    target_price = None
    stop_loss_price = None

    if "--target" in args:
        idx = args.index("--target")
        if idx + 1 < len(args):
            try:
                target_price = Decimal(args[idx + 1])
            except Exception:
                console.print(f"[red]Invalid target price: {args[idx + 1]}[/red]")
                return CommandResult(success=False, error=f"Invalid target price")

    if "--stop-loss" in args:
        idx = args.index("--stop-loss")
        if idx + 1 < len(args):
            try:
                stop_loss_price = Decimal(args[idx + 1])
            except Exception:
                console.print(f"[red]Invalid stop-loss price: {args[idx + 1]}[/red]")
                return CommandResult(success=False, error=f"Invalid stop-loss price")

    if not target_price or not stop_loss_price:
        console.print("[yellow]Missing --target or --stop-loss[/yellow]")
        return CommandResult(success=False, error="Missing target or stop-loss price")

    oms_service = OmsService(
        gateway=broker_service.active_broker,
        trading_context=broker_service.trading_context,
    )

    try:
        # Step 1: Place entry order
        console.print(f"[cyan]📦 Placing bracket order for {symbol}...[/cyan]")
        console.print(f"[cyan]   Entry: {side.value} {quantity} @ MARKET[/cyan]")

        entry_order = oms_service.place_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type="MARKET",
        )

        console.print(f"[green]   ✅ Entry order placed: {entry_order.order_id}[/green]")

        # Determine exit side (opposite of entry)
        exit_side = Side.SELL if side == Side.BUY else Side.BUY

        # Step 2: Place target order (limit)
        console.print(f"[cyan]   Target: {exit_side.value} {quantity} @ ₹{target_price:,.2f}[/cyan]")
        target_order = oms_service.place_order(
            symbol=symbol,
            side=exit_side,
            quantity=quantity,
            price=target_price,
            order_type="LIMIT",
        )

        console.print(f"[green]   ✅ Target order placed: {target_order.order_id}[/green]")

        # Step 3: Place stop-loss order
        console.print(f"[cyan]   Stop Loss: {exit_side.value} {quantity} @ ₹{stop_loss_price:,.2f}[/cyan]")
        sl_order = oms_service.place_order(
            symbol=symbol,
            side=exit_side,
            quantity=quantity,
            price=stop_loss_price,
            order_type="STOP_LOSS",
        )

        console.print(f"[green]   ✅ Stop-loss order placed: {sl_order.order_id}[/green]")

        # Display bracket summary
        table = Table(title="📦 Bracket Order Summary", header_style="bold cyan")
        table.add_column("Leg", style="bold white")
        table.add_column("Order ID")
        table.add_column("Type")
        table.add_column("Price", justify="right")
        table.add_column("Status", justify="center")

        table.add_row(
            "Entry",
            entry_order.order_id,
            "MARKET",
            "Market",
            f"[yellow]{entry_order.status.value}[/yellow]",
        )
        table.add_row(
            "Target",
            target_order.order_id,
            "LIMIT",
            f"₹{target_price:,.2f}",
            f"[yellow]{target_order.status.value}[/yellow]",
        )
        table.add_row(
            "Stop Loss",
            sl_order.order_id,
            "STOP_LOSS",
            f"₹{stop_loss_price:,.2f}",
            f"[yellow]{sl_order.status.value}[/yellow]",
        )

        console.print(table)

        return CommandResult(
            success=True,
            data={
                "entry_order_id": entry_order.order_id,
                "target_order_id": target_order.order_id,
                "stop_loss_order_id": sl_order.order_id,
            },
        )

    except Exception as exc:
        console.print(f"[red]❌ Bracket order failed: {exc}[/red]")
        return CommandResult(success=False, error=str(exc))


def place_oco_order(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    """Place OCO (One Cancels Other) order.

    Usage:
        tradex oco-order RELIANCE SELL 10 --order1-price 2500 --order2-price 2350
    """
    if len(args) < 3:
        console.print("[yellow]Usage: tradex oco-order SYMBOL SIDE QTY --order1-price P1 --order2-price P2[/yellow]")
        return CommandResult(success=False, error="Missing required arguments")

    symbol = args[0].upper()
    try:
        side = Side(args[1].upper())
    except ValueError:
        return CommandResult(success=False, error=f"Invalid side: {args[1]}")

    try:
        quantity = int(args[2])
    except ValueError:
        return CommandResult(success=False, error=f"Invalid quantity: {args[2]}")

    order1_price = None
    order2_price = None

    if "--order1-price" in args:
        idx = args.index("--order1-price")
        if idx + 1 < len(args):
            order1_price = Decimal(args[idx + 1])

    if "--order2-price" in args:
        idx = args.index("--order2-price")
        if idx + 1 < len(args):
            order2_price = Decimal(args[idx + 1])

    if not order1_price or not order2_price:
        return CommandResult(success=False, error="Missing order1-price or order2-price")

    oms_service = OmsService(
        gateway=broker_service.active_broker,
        trading_context=broker_service.trading_context,
    )

    try:
        console.print(f"[cyan]🔀 Placing OCO order for {symbol}...[/cyan]")

        # Place both orders
        console.print(f"[cyan]   Order 1: {side.value} {quantity} @ ₹{order1_price:,.2f}[/cyan]")
        order1 = oms_service.place_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=order1_price,
            order_type="LIMIT",
        )
        console.print(f"[green]   ✅ Order 1 placed: {order1.order_id}[/green]")

        console.print(f"[cyan]   Order 2: {side.value} {quantity} @ ₹{order2_price:,.2f}[/cyan]")
        order2 = oms_service.place_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=order2_price,
            order_type="LIMIT",
        )
        console.print(f"[green]   ✅ Order 2 placed: {order2.order_id}[/green]")

        # Display OCO summary
        table = Table(title="🔀 OCO Order Summary", header_style="bold magenta")
        table.add_column("Order", style="bold white")
        table.add_column("Order ID")
        table.add_column("Price", justify="right")
        table.add_column("Status")

        table.add_row("Order 1", order1.order_id, f"₹{order1_price:,.2f}", order1.status.value)
        table.add_row("Order 2", order2.order_id, f"₹{order2_price:,.2f}", order2.status.value)

        console.print(table)
        console.print("[yellow]Note: Manually cancel the other order when one fills[/yellow]")

        return CommandResult(
            success=True,
            data={
                "order1_id": order1.order_id,
                "order2_id": order2.order_id,
            },
        )

    except Exception as exc:
        console.print(f"[red]❌ OCO order failed: {exc}[/red]")
        return CommandResult(success=False, error=str(exc))


def place_basket_order(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    """Place basket order from CSV file.

    Usage:
        tradex basket-order --file basket.csv
    """
    from pathlib import Path
    import csv

    file_path = None
    if "--file" in args:
        idx = args.index("--file")
        if idx + 1 < len(args):
            file_path = args[idx + 1]
        else:
            return CommandResult(success=False, error="Missing file path")
    else:
        return CommandResult(success=False, error="Missing --file argument")

    csv_path = Path(file_path)
    if not csv_path.exists():
        return CommandResult(success=False, error=f"File not found: {file_path}")

    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            orders = list(reader)
    except Exception as exc:
        return CommandResult(success=False, error=f"Failed to read CSV: {exc}")

    if not orders:
        return CommandResult(success=False, error="Empty CSV file")

    console.print(f"[cyan]📦 Placing basket order with {len(orders)} symbols...[/cyan]")

    oms_service = OmsService(
        gateway=broker_service.active_broker,
        trading_context=broker_service.trading_context,
    )

    results = []
    success_count = 0
    failure_count = 0

    for i, order_data in enumerate(orders, 1):
        try:
            symbol = order_data.get("symbol", "").upper()
            side = Side(order_data.get("side", "BUY").upper())
            quantity = int(order_data.get("quantity", 0))

            console.print(f"[cyan][{i}/{len(orders)}] {side.value} {quantity} {symbol}[/cyan]")

            order = oms_service.place_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type="MARKET",
            )

            results.append({"symbol": symbol, "status": "success", "order_id": order.order_id})
            success_count += 1
            console.print(f"[green]   ✅ Placed: {order.order_id}[/green]")

        except Exception as exc:
            results.append({"symbol": order_data.get("symbol", "UNKNOWN"), "status": "failed", "error": str(exc)})
            failure_count += 1
            console.print(f"[red]   ❌ Failed: {exc}[/red]")

    # Display summary
    summary_table = Table(title="📊 Basket Order Summary", header_style="bold cyan")
    summary_table.add_column("Metric", style="bold white")
    summary_table.add_column("Count", justify="center")

    summary_table.add_row("Total Orders", str(len(orders)))
    summary_table.add_row("Successful", f"[green]{success_count}[/green]")
    summary_table.add_row("Failed", f"[red]{failure_count}[/red]")

    console.print(summary_table)

    return CommandResult(
        success=failure_count == 0,
        data={
            "total": len(orders),
            "successful": success_count,
            "failed": failure_count,
            "results": results,
        },
    )
