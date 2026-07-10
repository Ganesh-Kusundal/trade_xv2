"""CLI commands for advanced order composition patterns.

Implements bracket orders, OCO, basket orders, and other advanced patterns
using ExecutionComposer for multi-broker routing and quota management.

Commands:
    tradex bracket-order SYMBOL SIDE QTY --target PRICE --stop-loss PRICE
    tradex oco-order SYMBOL SIDE QTY --order1-price P1 --order2-price P2
    tradex basket-order --file basket.csv
"""

from __future__ import annotations

import csv
import logging
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

from infrastructure.io.async_compat import run_async_compat
from interface.ui.commands.argparse_helpers import parse_flag
from interface.ui.commands.registry import CommandResult
from interface.ui.composer_helpers import get_execution_composer
from interface.ui.services.broker_service import BrokerService
from domain import OrderType, ProductType, Side
from domain.orders.requests import OrderRequest

if TYPE_CHECKING:
    from application.composer.execution import ExecutionComposer

logger = logging.getLogger(__name__)


def _get_execution_composer(broker_service: BrokerService) -> ExecutionComposer:
    return get_execution_composer()


def _await_in_sync_context(coro):
    return run_async_compat(coro, fire_and_forget=False)


def place_bracket_order(
    args: list[str], broker_service: BrokerService, console: Console
) -> CommandResult:
    """Place bracket order: entry + target + stop loss via ExecutionComposer.

    Usage:
        tradex bracket-order RELIANCE BUY 10 --target 2500 --stop-loss 2400
    """
    if len(args) < 3:
        console.print(
            "[yellow]Usage: tradex bracket-order SYMBOL SIDE QTY --target PRICE --stop-loss PRICE[/yellow]"
        )
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

    target_val = parse_flag(args, "--target")
    if target_val is not None:
        try:
            target_price = Decimal(target_val)
        except Exception:
            console.print(f"[red]Invalid target price: {target_val}[/red]")
            return CommandResult(success=False, error="Invalid target price")

    sl_val = parse_flag(args, "--stop-loss")
    if sl_val is not None:
        try:
            stop_loss_price = Decimal(sl_val)
        except Exception:
            console.print(f"[red]Invalid stop-loss price: {sl_val}[/red]")
            return CommandResult(success=False, error="Invalid stop-loss price")

    if not target_price or not stop_loss_price:
        console.print("[yellow]Missing --target or --stop-loss[/yellow]")
        return CommandResult(success=False, error="Missing target or stop-loss price")

    # Get ExecutionComposer (lazy-loaded, cached)
    try:
        composer = _get_execution_composer(broker_service)
    except Exception as exc:
        logger.exception("Failed to initialize ExecutionComposer")
        return CommandResult(success=False, error=f"Composer initialization failed: {exc}")

    try:
        # Step 1: Place entry order
        console.print(f"[cyan]📦 Placing bracket order for {symbol}...[/cyan]")
        console.print(f"[cyan]   Entry: {side.value} {quantity} @ MARKET[/cyan]")

        entry_request = OrderRequest(
            symbol=symbol,
            transaction_type=side,
            quantity=quantity,
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
        )
        entry_response = _await_in_sync_context(composer.place_order(entry_request))
        console.print(f"[green]   ✅ Entry order placed: {entry_response.order_id}[/green]")

        # Determine exit side (opposite of entry)
        exit_side = Side.SELL if side == Side.BUY else Side.BUY

        # Step 2: Place target order (limit)
        console.print(
            f"[cyan]   Target: {exit_side.value} {quantity} @ ₹{target_price:,.2f}[/cyan]"
        )
        target_request = OrderRequest(
            symbol=symbol,
            transaction_type=exit_side,
            quantity=quantity,
            price=target_price,
            order_type=OrderType.LIMIT,
            product_type=ProductType.INTRADAY,
        )
        target_response = _await_in_sync_context(composer.place_order(target_request))
        console.print(f"[green]   ✅ Target order placed: {target_response.order_id}[/green]")

        # Step 3: Place stop-loss order
        console.print(
            f"[cyan]   Stop Loss: {exit_side.value} {quantity} @ ₹{stop_loss_price:,.2f}[/cyan]"
        )
        sl_request = OrderRequest(
            symbol=symbol,
            transaction_type=exit_side,
            quantity=quantity,
            price=stop_loss_price,
            order_type=OrderType.STOP_LOSS,
            product_type=ProductType.INTRADAY,
        )
        sl_response = _await_in_sync_context(composer.place_order(sl_request))
        console.print(f"[green]   ✅ Stop-loss order placed: {sl_response.order_id}[/green]")

        # Display bracket summary
        table = Table(title="📦 Bracket Order Summary", header_style="bold cyan")
        table.add_column("Leg", style="bold white")
        table.add_column("Order ID")
        table.add_column("Type")
        table.add_column("Price", justify="right")
        table.add_column("Status", justify="center")

        table.add_row(
            "Entry",
            entry_response.order_id,
            "MARKET",
            "Market",
            f"[yellow]{entry_response.status}[/yellow]",
        )
        table.add_row(
            "Target",
            target_response.order_id,
            "LIMIT",
            f"₹{target_price:,.2f}",
            f"[yellow]{target_response.status}[/yellow]",
        )
        table.add_row(
            "Stop Loss",
            sl_response.order_id,
            "STOP_LOSS",
            f"₹{stop_loss_price:,.2f}",
            f"[yellow]{sl_response.status}[/yellow]",
        )

        console.print(table)

        return CommandResult(
            success=True,
            data={
                "entry_order_id": entry_response.order_id,
                "target_order_id": target_response.order_id,
                "stop_loss_order_id": sl_response.order_id,
            },
        )

    except Exception as exc:
        console.print(f"[red]❌ Bracket order failed: {exc}[/red]")
        return CommandResult(success=False, error=str(exc))


def place_oco_order(
    args: list[str], broker_service: BrokerService, console: Console
) -> CommandResult:
    """Place OCO (One Cancels Other) order via ExecutionComposer.

    Usage:
        tradex oco-order RELIANCE SELL 10 --order1-price 2500 --order2-price 2350
    """
    if len(args) < 3:
        console.print(
            "[yellow]Usage: tradex oco-order SYMBOL SIDE QTY --order1-price P1 --order2-price P2[/yellow]"
        )
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

    o1_val = parse_flag(args, "--order1-price")
    if o1_val is not None:
        order1_price = Decimal(o1_val)

    o2_val = parse_flag(args, "--order2-price")
    if o2_val is not None:
        order2_price = Decimal(o2_val)

    if not order1_price or not order2_price:
        return CommandResult(success=False, error="Missing order1-price or order2-price")

    # Get ExecutionComposer (lazy-loaded, cached)
    try:
        composer = _get_execution_composer(broker_service)
    except Exception as exc:
        logger.exception("Failed to initialize ExecutionComposer")
        return CommandResult(success=False, error=f"Composer initialization failed: {exc}")

    try:
        console.print(f"[cyan]🔀 Placing OCO order for {symbol}...[/cyan]")

        # Place both orders
        console.print(f"[cyan]   Order 1: {side.value} {quantity} @ ₹{order1_price:,.2f}[/cyan]")
        order1_request = OrderRequest(
            symbol=symbol,
            transaction_type=side,
            quantity=quantity,
            price=order1_price,
            order_type=OrderType.LIMIT,
            product_type=ProductType.INTRADAY,
        )
        order1_response = _await_in_sync_context(composer.place_order(order1_request))
        console.print(f"[green]   ✅ Order 1 placed: {order1_response.order_id}[/green]")

        console.print(f"[cyan]   Order 2: {side.value} {quantity} @ ₹{order2_price:,.2f}[/cyan]")
        order2_request = OrderRequest(
            symbol=symbol,
            transaction_type=side,
            quantity=quantity,
            price=order2_price,
            order_type=OrderType.LIMIT,
            product_type=ProductType.INTRADAY,
        )
        order2_response = _await_in_sync_context(composer.place_order(order2_request))
        console.print(f"[green]   ✅ Order 2 placed: {order2_response.order_id}[/green]")

        # Display OCO summary
        table = Table(title="🔀 OCO Order Summary", header_style="bold magenta")
        table.add_column("Order", style="bold white")
        table.add_column("Order ID")
        table.add_column("Price", justify="right")
        table.add_column("Status")

        table.add_row("Order 1", order1_response.order_id, f"₹{order1_price:,.2f}", order1_response.status)
        table.add_row("Order 2", order2_response.order_id, f"₹{order2_price:,.2f}", order2_response.status)

        console.print(table)
        console.print("[yellow]Note: Manually cancel the other order when one fills[/yellow]")

        return CommandResult(
            success=True,
            data={
                "order1_id": order1_response.order_id,
                "order2_id": order2_response.order_id,
            },
        )

    except Exception as exc:
        console.print(f"[red]❌ OCO order failed: {exc}[/red]")
        return CommandResult(success=False, error=str(exc))


def place_basket_order(
    args: list[str], broker_service: BrokerService, console: Console
) -> CommandResult:
    """Place basket order from CSV file via ExecutionComposer.

    Usage:
        tradex basket-order --file basket.csv
    """
    file_path = parse_flag(args, "--file")
    if file_path is None:
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

    # Get ExecutionComposer (lazy-loaded, cached)
    try:
        composer = _get_execution_composer(broker_service)
    except Exception as exc:
        logger.exception("Failed to initialize ExecutionComposer")
        return CommandResult(success=False, error=f"Composer initialization failed: {exc}")

    results = []
    success_count = 0
    failure_count = 0

    for i, order_data in enumerate(orders, 1):
        try:
            symbol = order_data.get("symbol", "").upper()
            side = Side(order_data.get("side", "BUY").upper())
            quantity = int(order_data.get("quantity", 0))

            console.print(f"[cyan][{i}/{len(orders)}] {side.value} {quantity} {symbol}[/cyan]")

            # Build OrderRequest for ExecutionComposer
            request = OrderRequest(
                symbol=symbol,
                transaction_type=side,
                quantity=quantity,
                order_type=OrderType.MARKET,
                product_type=ProductType.INTRADAY,
            )

            # Execute via composer (async -> sync bridge)
            response = _await_in_sync_context(composer.place_order(request))

            results.append({"symbol": symbol, "status": "success", "order_id": response.order_id})
            success_count += 1
            console.print(f"[green]   ✅ Placed: {response.order_id}[/green]")

        except Exception as exc:
            results.append(
                {
                    "symbol": order_data.get("symbol", "UNKNOWN"),
                    "status": "failed",
                    "error": str(exc),
                }
            )
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
