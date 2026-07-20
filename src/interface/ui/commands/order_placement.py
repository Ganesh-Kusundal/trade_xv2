"""CLI commands for order placement, modification, and cancellation.

Exposes the ExecutionComposer order lifecycle through CLI with routing,
quota management, and multi-broker support.

Commands:
    tradex place-order SYMBOL SIDE QUANTITY [options]
    tradex cancel-order ORDER_ID
    tradex modify-order ORDER_ID [options]
    tradex place-orders --file orders.csv
"""

from __future__ import annotations

import csv
import logging
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

from domain import OrderType, ProductType, Side
from domain.orders.requests import ModifyOrderRequest, OrderRequest
from infrastructure.io.async_compat import run_async_compat
from interface.ui.commands.argparse_helpers import parse_flag
from interface.ui.commands.registry import CommandResult
from interface.ui.composer_helpers import get_execution_composer
from interface.ui.services.broker_service import BrokerService

if TYPE_CHECKING:
    from application.composer.execution import ExecutionComposer

logger = logging.getLogger(__name__)


def _get_execution_composer(broker_service: BrokerService) -> ExecutionComposer:
    return get_execution_composer()


def _await_in_sync_context(coro):
    return run_async_compat(coro, fire_and_forget=False)


def place_order(
    args: list[str],
    broker_service: BrokerService,
    console: Console,
) -> CommandResult:
    """Place a single order through ExecutionComposer.

    Usage:
        tradex place-order RELIANCE BUY 10 --type MARKET --exchange NSE
        tradex place-order NIFTY24600CE SELL 75 --type LIMIT --price 150.00 --exchange NFO
    """
    if len(args) < 3:
        console.print(
            "[yellow]Usage: tradex place-order SYMBOL SIDE QUANTITY [--type TYPE] [--price PRICE] [--exchange EXCHANGE] [--product PRODUCT][/yellow]"
        )
        return CommandResult(
            success=False, error="Missing required arguments: SYMBOL SIDE QUANTITY"
        )

    symbol = args[0].upper()
    try:
        side = Side(args[1].upper())
    except ValueError:
        console.print(f"[red]Invalid side: {args[1]}. Must be BUY or SELL[/red]")
        return CommandResult(success=False, error=f"Invalid side: {args[1]}")

    try:
        quantity = int(args[2])
        if quantity <= 0:
            raise ValueError
    except ValueError:
        console.print(f"[red]Invalid quantity: {args[2]}. Must be positive integer[/red]")
        return CommandResult(success=False, error=f"Invalid quantity: {args[2]}")

    order_type = OrderType.MARKET
    price = Decimal("0")
    exchange = "NSE"
    product_type = ProductType.INTRADAY

    type_val = parse_flag(args, "--type")
    if type_val is not None:
        try:
            order_type = OrderType(type_val.upper())
        except ValueError:
            console.print(f"[red]Invalid order type: {type_val}[/red]")
            return CommandResult(success=False, error=f"Invalid order type: {type_val}")

    price_val = parse_flag(args, "--price")
    if price_val is not None:
        try:
            price = Decimal(price_val)
        except Exception:
            console.print(f"[red]Invalid price: {price_val}[/red]")
            return CommandResult(success=False, error=f"Invalid price: {price_val}")

    exchange_val = parse_flag(args, "--exchange")
    if exchange_val is not None:
        exchange = exchange_val.upper()

    product_val = parse_flag(args, "--product")
    if product_val is not None:
        try:
            product_type = ProductType(product_val.upper())
        except ValueError:
            console.print(f"[red]Invalid product type: {product_val}[/red]")
            return CommandResult(success=False, error=f"Invalid product type: {product_val}")

    try:
        console.print(
            f"[cyan]Placing order via OMS spine: "
            f"{side.value} {quantity} {symbol} @ {order_type.value}[/cyan]"
        )

        composer = _get_execution_composer(broker_service)

        request = OrderRequest(
            symbol=symbol,
            exchange=exchange,
            transaction_type=side,
            quantity=quantity,
            price=price if order_type != OrderType.MARKET else Decimal("0"),
            order_type=order_type,
            product_type=product_type,
        )

        response = _await_in_sync_context(composer.place_order(request))

        if not response.success:
            console.print(f"[red]❌ Order Failed: {response.error}[/red]")
            return CommandResult(success=False, error=response.error or "rejected")

        order = getattr(response, "order", None)
        order_id = (
            getattr(response, "order_id", None)
            or (getattr(order, "order_id", None) if order else None)
            or "N/A"
        )
        status_val = (
            getattr(response, "status", None)
            or (getattr(order, "status", None) if order else None)
            or "UNKNOWN"
        )
        if hasattr(status_val, "value"):
            status_val = status_val.value

        table = Table(title="✅ Order Placed (OMS)", header_style="bold green")
        table.add_column("Field", style="bold white")
        table.add_column("Value", style="green")
        table.add_row("Order ID", str(order_id))
        table.add_row("Symbol", symbol)
        table.add_row("Exchange", exchange)
        table.add_row("Side", f"[green]{side.value}[/green]")
        table.add_row("Type", order_type.value)
        table.add_row("Quantity", str(quantity))
        table.add_row("Price", f"₹{price:,.2f}" if price > 0 else "MARKET")
        table.add_row("Status", f"[yellow]{status_val}[/yellow]")
        table.add_row("Correlation", str(getattr(order, "correlation_id", "") or ""))
        console.print(table)

        return CommandResult(
            success=True,
            data={
                "order_id": order_id,
                "symbol": symbol,
                "side": side.value,
                "quantity": quantity,
                "status": status_val,
            },
        )

    except Exception as exc:
        logger.exception("Order placement failed")
        console.print(f"[red]❌ Order Failed: {exc}[/red]")
        return CommandResult(success=False, error=str(exc))


def cancel_order(
    args: list[str],
    broker_service: BrokerService,
    console: Console,
) -> CommandResult:
    """Cancel an existing order via ExecutionComposer.

    Usage:
        tradex cancel-order <order_id>
    """
    if not args:
        console.print("[yellow]Usage: tradex cancel-order <order_id>[/yellow]")
        return CommandResult(success=False, error="Missing order ID")

    order_id = args[0]

    try:
        composer = _get_execution_composer(broker_service)
    except Exception as exc:
        logger.exception("Failed to initialize ExecutionComposer")
        return CommandResult(success=False, error=f"Composer initialization failed: {exc}")

    try:
        console.print(f"[cyan]Cancelling order {order_id}...[/cyan]")

        # Execute via composer (async -> sync bridge)
        response = _await_in_sync_context(composer.cancel_order(order_id))

        if response.success:
            console.print(f"[green]✅ Order {order_id} cancelled successfully[/green]")
            return CommandResult(success=True, data={"order_id": order_id, "status": "cancelled"})
        else:
            console.print(f"[red]❌ Failed to cancel order {order_id}[/red]")
            return CommandResult(
                success=False,
                error=f"Failed to cancel order {order_id}: {response.error}",
            )

    except Exception as exc:
        logger.exception("Order cancellation failed")
        console.print(f"[red]❌ Cancellation Failed: {exc}[/red]")
        return CommandResult(success=False, error=str(exc))


def modify_order(
    args: list[str],
    broker_service: BrokerService,
    console: Console,
) -> CommandResult:
    """Modify an existing order (price, quantity) via ExecutionComposer.

    Usage:
        tradex modify-order <order_id> --price 155.00 --quantity 100
    """
    if not args:
        console.print(
            "[yellow]Usage: tradex modify-order <order_id> [--price PRICE] [--quantity QTY][/yellow]"
        )
        return CommandResult(success=False, error="Missing order ID")

    order_id = args[0]

    # Parse optional flags
    new_price: Decimal | None = None
    new_quantity: int | None = None

    price_val = parse_flag(args, "--price")
    if price_val is not None:
        try:
            new_price = Decimal(price_val)
        except Exception:
            console.print(f"[red]Invalid price: {price_val}[/red]")
            return CommandResult(success=False, error=f"Invalid price: {price_val}")

    qty_val = parse_flag(args, "--quantity")
    if qty_val is not None:
        try:
            new_quantity = int(qty_val)
            if new_quantity <= 0:
                raise ValueError
        except ValueError:
            console.print(f"[red]Invalid quantity: {qty_val}[/red]")
            return CommandResult(success=False, error=f"Invalid quantity: {qty_val}")

    if new_price is None and new_quantity is None:
        console.print("[yellow]No modifications specified. Use --price or --quantity[/yellow]")
        return CommandResult(success=False, error="No modifications specified")

    try:
        composer = _get_execution_composer(broker_service)
    except Exception as exc:
        logger.exception("Failed to initialize ExecutionComposer")
        return CommandResult(success=False, error=f"Composer initialization failed: {exc}")

    try:
        console.print(f"[cyan]Modifying order {order_id}...[/cyan]")
        if new_price is not None:
            console.print(f"[cyan]  New price: ₹{new_price:,.2f}[/cyan]")
        if new_quantity is not None:
            console.print(f"[cyan]  New quantity: {new_quantity}[/cyan]")

        request = ModifyOrderRequest(
            order_id=order_id,
            price=new_price,
            quantity=new_quantity,
        )

        # Execute via composer (async -> sync bridge)
        response = _await_in_sync_context(composer.modify_order(request))

        if response.success:
            console.print(f"[green]✅ Order {order_id} modified successfully[/green]")
            return CommandResult(
                success=True,
                data={
                    "order_id": order_id,
                    "new_price": str(new_price) if new_price else None,
                    "new_quantity": new_quantity,
                },
            )
        else:
            console.print(f"[red]❌ Failed to modify order {order_id}[/red]")
            return CommandResult(
                success=False, error=f"Failed to modify order {order_id}: {response.error}"
            )

    except Exception as exc:
        logger.exception("Order modification failed")
        console.print(f"[red]❌ Modification Failed: {exc}[/red]")
        return CommandResult(success=False, error=str(exc))


def place_orders_batch(
    args: list[str],
    broker_service: BrokerService,
    console: Console,
) -> CommandResult:
    """Place multiple orders from a CSV file via ExecutionComposer.

    CSV format:
        symbol,side,quantity,type,price,exchange,product

    Usage:
        tradex place-orders --file orders.csv
    """
    file_path = parse_flag(args, "--file")
    if file_path is None:
        console.print("[yellow]Usage: tradex place-orders --file <csv_file>[/yellow]")
        return CommandResult(success=False, error="Missing --file argument")

    csv_path = Path(file_path)
    if not csv_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        return CommandResult(success=False, error=f"File not found: {file_path}")

    # Read CSV
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            orders = list(reader)
    except Exception as exc:
        console.print(f"[red]Failed to read CSV: {exc}[/red]")
        return CommandResult(success=False, error=f"Failed to read CSV: {exc}")

    if not orders:
        console.print("[yellow]No orders found in CSV file[/yellow]")
        return CommandResult(success=False, error="Empty CSV file")

    console.print(f"[cyan]Placing {len(orders)} orders from {file_path}...[/cyan]")

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
            order_type = OrderType(order_data.get("type", "MARKET").upper())
            price = Decimal(order_data.get("price", "0"))
            exchange = order_data.get("exchange", "NSE").upper()
            product_type = ProductType(order_data.get("product", "INTRADAY").upper())

            console.print(
                f"[cyan][{i}/{len(orders)}] Placing: {side.value} {quantity} {symbol}[/cyan]"
            )

            # Build OrderRequest for ExecutionComposer
            request = OrderRequest(
                symbol=symbol,
                exchange=exchange,
                transaction_type=side,
                quantity=quantity,
                price=price if order_type != OrderType.MARKET else Decimal("0"),
                order_type=order_type,
                product_type=product_type,
            )

            # Execute via composer (async -> sync bridge)
            response = _await_in_sync_context(composer.place_order(request))

            results.append({"symbol": symbol, "status": "success", "order_id": response.order_id})
            success_count += 1
            console.print(f"[green]  ✅ Placed: {response.order_id}[/green]")

        except Exception as exc:
            results.append(
                {
                    "symbol": order_data.get("symbol", "UNKNOWN"),
                    "status": "failed",
                    "error": str(exc),
                }
            )
            failure_count += 1
            console.print(f"[red]  ❌ Failed: {exc}[/red]")

    # Display summary
    summary_table = Table(title="📊 Batch Order Summary", header_style="bold cyan")
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
