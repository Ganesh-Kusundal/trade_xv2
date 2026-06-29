"""CLI market data handlers extracted from cli/main.py (REF-013 inline extraction).

Previously ``_handle_quote``, ``_handle_depth``, ``_handle_history``,
``_handle_option_chain``, ``_handle_futures``, and ``_handle_stream``
lived inline in ``cli/main.py`` — the CLI entry point.  They are now
importable from this module, keeping ``main.py`` focused on routing
and lifecycle.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from rich.console import Console
from rich.table import Table

from cli.commands import market as cmd_market
from cli.commands import oms as cmd_oms
from cli.commands import validate as cmd_validate
from cli.commands import validate_history as cmd_validate_history
from cli.commands import validate_option_chain as cmd_validate_option_chain
from cli.commands.registry import CommandResult
from cli.services.broker_service import BrokerService
from domain import DepthLevel, MarketDepth
from domain.symbols import normalize_symbol


def handle_quote(
    args: list[str], broker_service: BrokerService, console: Console
) -> CommandResult | None:
    if not args:
        console.print("[yellow]Usage: tradex quote <symbol>[/yellow]")
        return CommandResult(success=False, error="Missing symbol")
    symbol = args[0]
    gw = broker_service.active_broker
    if gw is None:
        return CommandResult(success=False, error="No broker gateway available. Check credentials.")
    quote = gw.quote(symbol)
    if quote is None:
        return CommandResult(success=False, error=f"No quote data for {symbol}")
    table = Table(title=f"Quote: {normalize_symbol(symbol)}", header_style="bold green")
    table.add_column("Metric", style="bold white")
    table.add_column("Value", justify="right")
    table.add_row("LTP", f"\u20b9{quote.ltp:,.2f}")
    table.add_row("Open", f"\u20b9{quote.open:,.2f}")
    table.add_row("High", f"\u20b9{quote.high:,.2f}")
    table.add_row("Low", f"\u20b9{quote.low:,.2f}")
    table.add_row("Close", f"\u20b9{quote.close:,.2f}")
    table.add_row("Volume", f"{quote.volume:,}")
    table.add_row("Change", f"\u20b9{quote.change:,.2f}")
    console.print(table)
    return CommandResult(
        success=True,
        data={
            "symbol": symbol,
            "ltp": str(quote.ltp),
            "open": str(quote.open),
            "high": str(quote.high),
            "low": str(quote.low),
            "close": str(quote.close),
            "volume": quote.volume,
            "change": str(quote.change),
        },
    )


def handle_depth(
    args: list[str], broker_service: BrokerService, console: Console
) -> CommandResult | None:
    if not args:
        console.print("[yellow]Usage: tradex depth <symbol>[/yellow]")
        return CommandResult(success=False, error="Missing symbol")
    symbol = args[0]
    gw = broker_service.active_broker
    if gw is None:
        return CommandResult(success=False, error="No broker gateway available. Check credentials.")
    depth_obj: Any = gw.depth(symbol)
    if depth_obj is None:
        return CommandResult(success=False, error=f"No depth data for {symbol}")
    depth: MarketDepth = depth_obj
    bids: list[DepthLevel] = list(depth.bids) if depth.bids else []
    asks: list[DepthLevel] = list(depth.asks) if depth.asks else []
    if not bids and not asks:
        return CommandResult(success=False, error=f"No depth data for {symbol}")
    table = Table(title=f"Market Depth: {normalize_symbol(symbol)}", header_style="bold magenta")
    table.add_column("Bid Qty", style="green", justify="right")
    table.add_column("Bid Price", style="bold green", justify="right")
    table.add_column("Ask Price", style="bold red", justify="right")
    table.add_column("Ask Qty", style="red", justify="right")
    levels = max(len(bids), len(asks))
    for i in range(levels):
        bid: DepthLevel | None = bids[i] if i < len(bids) else None
        ask: DepthLevel | None = asks[i] if i < len(asks) else None
        table.add_row(
            f"{bid.quantity:,}" if bid else "-",
            f"\u20b9{bid.price:,.2f}" if bid else "-",
            f"\u20b9{ask.price:,.2f}" if ask else "-",
            f"{ask.quantity:,}" if ask else "-",
        )
    console.print(table)
    return CommandResult(success=True)


def handle_history(
    args: list[str], broker_service: BrokerService, console: Console
) -> CommandResult | None:
    if not args:
        console.print("[yellow]Usage: tradex history <symbol>[/yellow]")
        return CommandResult(success=False, error="Missing symbol")
    symbol = args[0]
    gw = broker_service.active_broker
    if gw is None:
        return CommandResult(success=False, error="No broker gateway available. Check credentials.")
    if not hasattr(gw, "history"):
        return CommandResult(
            success=False,
            error=f"Broker '{broker_service.active_broker_name}' does not support historical data",
        )
    history_fn: Any = getattr(getattr(gw, "historical", None), "history", gw.history)
    to_date = date.today()
    from_date = to_date - timedelta(days=10)
    df = history_fn(
        symbol,
        "NSE",
        from_date=from_date.strftime("%Y-%m-%d"),
        to_date=to_date.strftime("%Y-%m-%d"),
        timeframe="1D",
    )
    if df is None or df.empty:
        return CommandResult(success=False, error=f"No history data for {symbol}")
    table = Table(title=f"History: {normalize_symbol(symbol)} (last 5 days)", header_style="bold magenta")
    table.add_column("Date", style="bold white")
    table.add_column("Open", justify="right")
    table.add_column("High", justify="right")
    table.add_column("Low", justify="right")
    table.add_column("Close", justify="right")
    table.add_column("Volume", justify="right")
    for ts, open_val, high_val, low_val, close_val, volume in zip(
        df["timestamp"].tail(5),
        df["open"].tail(5),
        df["high"].tail(5),
        df["low"].tail(5),
        df["close"].tail(5),
        df["volume"].tail(5),
        strict=False,
    ):
        date_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)
        table.add_row(
            date_str,
            f"\u20b9{open_val:,.2f}",
            f"\u20b9{high_val:,.2f}",
            f"\u20b9{low_val:,.2f}",
            f"\u20b9{close_val:,.2f}",
            f"{int(volume):,}",
        )
    console.print(table)
    console.print(f"[dim]{len(df)} candles total[/dim]")
    return CommandResult(success=True, data={"symbol": symbol, "candles": len(df)})


def handle_option_chain(
    args: list[str], broker_service: BrokerService, console: Console
) -> CommandResult | None:
    if not args:
        console.print("[yellow]Usage: tradex option-chain <symbol> [--expiry <date>][/yellow]")
        return CommandResult(success=False, error="Missing symbol")
    symbol = args[0]
    expiry = None
    if "--expiry" in args:
        idx = args.index("--expiry")
        if idx + 1 < len(args):
            expiry = args[idx + 1]
    cmd_market.show_option_chain(broker_service, symbol, console, expiry)
    return CommandResult(success=True)


def handle_futures(
    args: list[str], broker_service: BrokerService, console: Console
) -> CommandResult | None:
    if not args:
        console.print("[yellow]Usage: tradex futures <symbol>[/yellow]")
        return CommandResult(success=False, error="Missing symbol")
    symbol = args[0]
    cmd_market.show_futures(broker_service, symbol, console)
    return CommandResult(success=True)


def handle_stream(
    args: list[str], broker_service: BrokerService, console: Console
) -> CommandResult | None:
    if not args:
        console.print("[yellow]Usage: tradex stream <symbol>[/yellow]")
        return CommandResult(success=False, error="Missing symbol")
    symbol = args[0]
    cmd_market.show_stream(broker_service, symbol, console)
    return CommandResult(success=True)


def handle_orders(
    args: list[str], broker_service: BrokerService, console: Console
) -> CommandResult | None:
    status_filter = args[0] if args else None
    cmd_oms.show_orders(broker_service, console, status_filter)
    return CommandResult(success=True)


def handle_validate(
    args: list[str], broker_service: BrokerService, console: Console
) -> CommandResult | None:
    if args and args[0] == "history":
        cmd_validate_history.run(args[1:], broker_service, console)
    elif args and args[0] == "option-chain":
        cmd_validate_option_chain.run(args[1:], broker_service, console)
    else:
        cmd_validate.run(args, broker_service, console)
    return CommandResult(success=True)
