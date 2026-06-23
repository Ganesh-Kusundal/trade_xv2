"""CLI commands for order placement, modification, and cancellation.

Exposes the central OMS order lifecycle through CLI with full risk checks,
idempotency, and event bus integration.

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

from rich.console import Console
from rich.table import Table

from domain import OrderType, ProductType, Side
from cli.commands.registry import CommandResult
from cli.services.broker_service import BrokerService
from cli.services.oms_service import OmsService

logger = logging.getLogger(__name__)


def place_order(
    args: list[str],
    broker_service: BrokerService,
    console: Console,
) -> CommandResult:
    """Place a single order through the central OMS.

    Usage:
        tradex place-order RELIANCE BUY 10 --type MARKET --exchange NSE
        tradex place-order NIFTY24600CE SELL 75 --type LIMIT --price 150.00 --exchange NFO
    """
    if len(args) < 3:
        console.print("[yellow]Usage: tradex place-order SYMBOL SIDE QUANTITY [--type TYPE] [--price PRICE] [--exchange EXCHANGE] [--product PRODUCT][/yellow]")
        return CommandResult(success=False, error="Missing required arguments: SYMBOL SIDE QUANTITY")

    # Parse positional arguments
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

    # Parse optional flags
    order_type = OrderType.MARKET
    price = Decimal("0")
    exchange = "NSE"
    product = ProductType.INTRADAY

    if "--type" in args:
        idx = args.index("--type")
        if idx + 1 < len(args):
            try:
                order_type = OrderType(args[idx + 1].upper())
            except ValueError:
                console.print(f"[red]Invalid order type: {args[idx + 1]}[/red]")
                return CommandResult(success=False, error=f"Invalid order type: {args[idx + 1]}")

    if "--price" in args:
        idx = args.index("--price")
        if idx + 1 < len(args):
            try:
                price = Decimal(args[idx + 1])
            except Exception:
                console.print(f"[red]Invalid price: {args[idx + 1]}[/red]")
                return CommandResult(success=False, error=f"Invalid price: {args[idx + 1]}")

    if "--exchange" in args:
        idx = args.index("--exchange")
        if idx + 1 < len(args):
            exchange = args[idx + 1].upper()

    if "--product" in args:
        idx = args.index("--product")
        if idx + 1 < len(args):
            try:
                product = ProductType(args[idx + 1].upper())
            except ValueError:
                console.print(f"[red]Invalid product type: {args[idx + 1]}[/red]")
                return CommandResult(success=False, error=f"Invalid product type: {args[idx + 1]}")

    # Create OMS service with TradingContext
    oms_service = OmsService(
        gateway=broker_service.active_broker,
        trading_context=broker_service.trading_context,
    )

    try:
        console.print(f"[cyan]Placing order: {side.value} {quantity} {symbol} @ {order_type.value}[/cyan]")

        order = oms_service.place_order(
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=price if order_type != OrderType.MARKET else Decimal("0"),
            order_type=order_type.value,
        )

        # Display success with Rich table
        table = Table(title="✅ Order Placed Successfully", header_style="bold green")
        table.add_column("Field", style="bold white")
        table.add_column("Value", style="green")
        table.add_row("Order ID", order.order_id or "N/A")
        table.add_row("Symbol", order.symbol)
        table.add_row("Exchange", exchange)
        table.add_row("Side", f"[green]{order.side.value}[/green]")
        table.add_row("Type", order.order_type.value)
        table.add_row("Quantity", str(order.quantity))
        table.add_row(
            "Price",
            f"₹{order.price:,.2f}" if order.price > 0 else "MARKET",
        )
        table.add_row("Status", f"[yellow]{order.status.value}[/yellow]")
        console.print(table)

        return CommandResult(
            success=True,
            data={
                "order_id": order.order_id,
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": order.quantity,
                "status": order.status.value,
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
    """Cancel an existing order.

    Usage:
        tradex cancel-order <order_id>
    """
    if not args:
        console.print("[yellow]Usage: tradex cancel-order <order_id>[/yellow]")
        return CommandResult(success=False, error="Missing order ID")

    order_id = args[0]

    oms_service = OmsService(
        gateway=broker_service.active_broker,
        trading_context=broker_service.trading_context,
    )

    try:
        console.print(f"[cyan]Cancelling order {order_id}...[/cyan]")

        success = oms_service.cancel_order(order_id)

        if success:
            console.print(f"[green]✅ Order {order_id} cancelled successfully[/green]")
            return CommandResult(success=True, data={"order_id": order_id, "status": "cancelled"})
        else:
            console.print(f"[red]❌ Failed to cancel order {order_id}[/red]")
            return CommandResult(
                success=False,
                error=f"Failed to cancel order {order_id}",
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
    """Modify an existing order (price, quantity).

    Usage:
        tradex modify-order <order_id> --price 155.00 --quantity 100
    """
    if not args:
        console.print("[yellow]Usage: tradex modify-order <order_id> [--price PRICE] [--quantity QTY][/yellow]")
        return CommandResult(success=False, error="Missing order ID")

    order_id = args[0]

    # Parse optional flags
    new_price: Decimal | None = None
    new_quantity: int | None = None

    if "--price" in args:
        idx = args.index("--price")
        if idx + 1 < len(args):
            try:
                new_price = Decimal(args[idx + 1])
            except Exception:
                console.print(f"[red]Invalid price: {args[idx + 1]}[/red]")
                return CommandResult(success=False, error=f"Invalid price: {args[idx + 1]}")

    if "--quantity" in args:
        idx = args.index("--quantity")
        if idx + 1 < len(args):
            try:
                new_quantity = int(args[idx + 1])
                if new_quantity <= 0:
                    raise ValueError
            except ValueError:
                console.print(f"[red]Invalid quantity: {args[idx + 1]}[/red]")
                return CommandResult(success=False, error=f"Invalid quantity: {args[idx + 1]}")

    if new_price is None and new_quantity is None:
        console.print("[yellow]No modifications specified. Use --price or --quantity[/yellow]")
        return CommandResult(success=False, error="No modifications specified")

    oms_service = OmsService(
        gateway=broker_service.active_broker,
        trading_context=broker_service.trading_context,
    )

    try:
        console.print(f"[cyan]Modifying order {order_id}...[/cyan]")
        if new_price is not None:
            console.print(f"[cyan]  New price: ₹{new_price:,.2f}[/cyan]")
        if new_quantity is not None:
            console.print(f"[cyan]  New quantity: {new_quantity}[/cyan]")

        # Note: OMS modify_order implementation may vary by broker
        # This assumes the gateway supports modification
        gw = broker_service.active_broker
        success = gw.modify_order(
            order_id=order_id,
            price=new_price,
            quantity=new_quantity,
        )

        if success:
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
            return CommandResult(success=False, error=f"Failed to modify order {order_id}")

    except Exception as exc:
        logger.exception("Order modification failed")
        console.print(f"[red]❌ Modification Failed: {exc}[/red]")
        return CommandResult(success=False, error=str(exc))


def place_orders_batch(
    args: list[str],
    broker_service: BrokerService,
    console: Console,
) -> CommandResult:
    """Place multiple orders from a CSV file.

    CSV format:
        symbol,side,quantity,type,price,exchange,product

    Usage:
        tradex place-orders --file orders.csv
    """
    file_path: str | None = None

    if "--file" in args:
        idx = args.index("--file")
        if idx + 1 < len(args):
            file_path = args[idx + 1]
        else:
            console.print("[red]Missing file path after --file[/red]")
            return CommandResult(success=False, error="Missing file path")
    else:
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
            order_type = OrderType(order_data.get("type", "MARKET").upper())
            price = Decimal(order_data.get("price", "0"))
            exchange = order_data.get("exchange", "NSE").upper()

            console.print(f"[cyan][{i}/{len(orders)}] Placing: {side.value} {quantity} {symbol}[/cyan]")

            order = oms_service.place_order(
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=quantity,
                price=price if order_type != OrderType.MARKET else Decimal("0"),
                order_type=order_type.value,
            )

            results.append({"symbol": symbol, "status": "success", "order_id": order.order_id})
            success_count += 1
            console.print(f"[green]  ✅ Placed: {order.order_id}[/green]")

        except Exception as exc:
            results.append({"symbol": order_data.get("symbol", "UNKNOWN"), "status": "failed", "error": str(exc)})
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
