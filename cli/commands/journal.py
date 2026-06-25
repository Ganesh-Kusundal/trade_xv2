"""Trade journal CLI commands."""

from __future__ import annotations

from datetime import datetime

from rich.console import Console
from rich.table import Table

from datalake.journal import TradeJournal


def run_journal(args: list[str], console: Console) -> None:
    """Manage trade journal."""
    if not args:
        _print_help(console)
        return

    command = args[0].lower()

    if command == "record":
        _record_trade(args[1:], console)
    elif command == "close":
        _close_trade(args[1:], console)
    elif command == "list":
        _list_trades(args[1:], console)
    elif command == "summary":
        _show_summary(args[1:], console)
    else:
        console.print(f"[yellow]Unknown command: {command}[/yellow]")
        _print_help(console)


def _print_help(console: Console) -> None:
    """Print help."""
    console.print("[bold]Trade Journal[/bold]")
    console.print("[dim]Commands:[/dim]")
    console.print(
        "  record --id ID --symbol SYM --strategy STR --entry-price P --quantity Q --side BUY|SELL"
    )
    console.print("  close --id ID --exit-price P")
    console.print("  list [--symbol SYM] [--strategy STR] [--status open|closed]")
    console.print("  summary [--strategy STR] [--symbol SYM]")


def _record_trade(args: list[str], console: Console) -> None:
    """Record a new trade."""
    params = {}
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--id" and index + 1 < len(args):
            params["trade_id"] = args[index + 1]
            index += 2
        elif arg == "--symbol" and index + 1 < len(args):
            params["symbol"] = args[index + 1]
            index += 2
        elif arg == "--strategy" and index + 1 < len(args):
            params["strategy"] = args[index + 1]
            index += 2
        elif arg == "--entry-price" and index + 1 < len(args):
            params["entry_price"] = float(args[index + 1])
            index += 2
        elif arg == "--quantity" and index + 1 < len(args):
            params["quantity"] = int(args[index + 1])
            index += 2
        elif arg == "--side" and index + 1 < len(args):
            params["side"] = args[index + 1].upper()
            index += 2
        elif arg == "--notes" and index + 1 < len(args):
            params["notes"] = args[index + 1]
            index += 2
        else:
            index += 1

    required = ["trade_id", "symbol", "strategy", "entry_price", "quantity", "side"]
    missing = [r for r in required if r not in params]
    if missing:
        console.print(f"[red]Missing required parameters: {', '.join(missing)}[/red]")
        return

    journal = TradeJournal()
    try:
        journal.record_trade(
            trade_id=params["trade_id"],
            symbol=params["symbol"],
            strategy=params["strategy"],
            entry_time=datetime.now(),
            entry_price=params["entry_price"],
            quantity=params["quantity"],
            side=params["side"],
            notes=params.get("notes"),
        )
        console.print(f"[green]Trade {params['trade_id']} recorded.[/green]")
    finally:
        journal.close()


def _close_trade(args: list[str], console: Console) -> None:
    """Close an open trade."""
    params = {}
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--id" and index + 1 < len(args):
            params["trade_id"] = args[index + 1]
            index += 2
        elif arg == "--exit-price" and index + 1 < len(args):
            params["exit_price"] = float(args[index + 1])
            index += 2
        elif arg == "--notes" and index + 1 < len(args):
            params["notes"] = args[index + 1]
            index += 2
        else:
            index += 1

    if "trade_id" not in params or "exit_price" not in params:
        console.print("[red]Usage: close --id ID --exit-price PRICE[/red]")
        return

    journal = TradeJournal()
    try:
        journal.close_trade(
            trade_id=params["trade_id"],
            exit_time=datetime.now(),
            exit_price=params["exit_price"],
            notes=params.get("notes"),
        )
        console.print(f"[green]Trade {params['trade_id']} closed.[/green]")
    finally:
        journal.close()


def _list_trades(args: list[str], console: Console) -> None:
    """List trades."""
    symbol = None
    strategy = None
    status = None

    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--symbol" and index + 1 < len(args):
            symbol = args[index + 1]
            index += 2
        elif arg == "--strategy" and index + 1 < len(args):
            strategy = args[index + 1]
            index += 2
        elif arg == "--status" and index + 1 < len(args):
            status = args[index + 1]
            index += 2
        else:
            index += 1

    journal = TradeJournal(read_only=True)
    try:
        trades = journal.get_trades(symbol=symbol, strategy=strategy, status=status)
        if not trades:
            console.print("[dim]No trades found.[/dim]")
            return

        table = Table(title="Trade Journal", header_style="bold cyan")
        table.add_column("ID", style="bold")
        table.add_column("Symbol")
        table.add_column("Strategy")
        table.add_column("Side")
        table.add_column("Entry", style="cyan")
        table.add_column("Exit", style="cyan")
        table.add_column("Qty")
        table.add_column("P&L", style="green")
        table.add_column("Status")

        for t in trades:
            pnl_style = "green" if (t.get("pnl") or 0) >= 0 else "red"
            table.add_row(
                t["trade_id"],
                t["symbol"],
                t["strategy"],
                t["side"],
                f"₹{t['entry_price']:.2f}",
                f"₹{t['exit_price']:.2f}" if t.get("exit_price") else "-",
                str(t["quantity"]),
                f"[{pnl_style}]₹{t['pnl']:.2f}[/{pnl_style}]" if t.get("pnl") else "-",
                t["status"],
            )

        console.print(table)
    finally:
        journal.close()


def _show_summary(args: list[str], console: Console) -> None:
    """Show trade summary."""
    strategy = None
    symbol = None

    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--strategy" and index + 1 < len(args):
            strategy = args[index + 1]
            index += 2
        elif arg == "--symbol" and index + 1 < len(args):
            symbol = args[index + 1]
            index += 2
        else:
            index += 1

    journal = TradeJournal(read_only=True)
    try:
        summary = journal.get_trade_summary(strategy=strategy, symbol=symbol)

        console.print("[bold]Trade Summary[/bold]")
        console.print(f"  Total Trades: {summary['total_trades']}")
        console.print(f"  Total P&L: ₹{summary['total_pnl']:.2f}")
        console.print(f"  Average P&L: ₹{summary['avg_pnl']:.2f}")
        console.print(f"  Win Rate: {summary['win_rate'] * 100:.1f}%")
        console.print(f"  Winning: {summary['winning_trades']}")
        console.print(f"  Losing: {summary['losing_trades']}")
    finally:
        journal.close()
