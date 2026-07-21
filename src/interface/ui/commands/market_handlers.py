"""CLI market data handlers extracted from cli/main.py (REF-013 inline extraction).

Previously ``_handle_quote``, ``_handle_depth``, ``_handle_history``,
``_handle_option_chain``, ``_handle_futures``, and ``_handle_stream``
lived inline in ``cli/main.py`` — the CLI entry point.  They are now
importable from this module, keeping ``main.py`` focused on routing
and lifecycle.
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from domain.entities import DepthLevel, MarketDepth
from domain.symbols import normalize_symbol
from interface.ui.commands import market as cmd_market
from interface.ui.commands import oms as cmd_oms
from interface.ui.commands import validate as cmd_validate
from interface.ui.commands import validate_history as cmd_validate_history
from interface.ui.commands import validate_option_chain as cmd_validate_option_chain
from interface.ui.commands._broker import broker_id_from
from interface.ui.commands.argparse_helpers import parse_flag, require_symbol
from interface.ui.commands.registry import CommandResult
from interface.ui.services.broker_ops import get_depth, get_history, get_quote
from interface.ui.services.broker_service import BrokerService
from interface.ui.services.renderers import render_depth, render_quote


def handle_quote(
    args: list[str], broker_service: BrokerService, console: Console
) -> CommandResult | None:
    result = require_symbol(args, broker_service, console, usage="tradex quote <symbol>")
    if isinstance(result, CommandResult):
        return result
    symbol, _gw = result
    try:
        quote = get_quote(broker_id_from(broker_service), symbol)
    except Exception as exc:
        return CommandResult(success=False, error=str(exc))
    if quote is None:
        return CommandResult(success=False, error=f"No quote data for {symbol}")
    render_quote(console, symbol, quote)
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
    result = require_symbol(args, broker_service, console, usage="tradex depth <symbol>")
    if isinstance(result, CommandResult):
        return result
    symbol, _gw = result
    try:
        depth_obj = get_depth(broker_id_from(broker_service), symbol)
    except Exception as exc:
        return CommandResult(success=False, error=str(exc))
    if depth_obj is None:
        return CommandResult(success=False, error=f"No depth data for {symbol}")
    depth: MarketDepth = depth_obj
    bids: list[DepthLevel] = list(depth.bids) if depth.bids else []
    asks: list[DepthLevel] = list(depth.asks) if depth.asks else []
    if not bids and not asks:
        return CommandResult(success=False, error=f"No depth data for {symbol}")
    render_depth(console, symbol, depth_obj)
    return CommandResult(success=True)


def handle_history(
    args: list[str], broker_service: BrokerService, console: Console
) -> CommandResult | None:
    result = require_symbol(args, broker_service, console, usage="tradex history <symbol>")
    if isinstance(result, CommandResult):
        return result
    symbol, _gw = result
    try:
        series = get_history(broker_id_from(broker_service), symbol, days=10)
    except Exception as exc:
        return CommandResult(success=False, error=str(exc))
    bars = getattr(series, "bars", None)
    if bars is None and hasattr(series, "to_dataframe"):
        df = series.to_dataframe()
    elif hasattr(series, "empty"):
        df = series
    else:
        # HistoricalSeries — convert via dataframe helper if present
        df = getattr(series, "df", None)
        if df is None and bars is not None:
            import pandas as pd

            df = pd.DataFrame(
                [
                    {
                        "timestamp": getattr(b, "timestamp", None),
                        "open": float(getattr(b, "open", 0)),
                        "high": float(getattr(b, "high", 0)),
                        "low": float(getattr(b, "low", 0)),
                        "close": float(getattr(b, "close", 0)),
                        "volume": int(getattr(b, "volume", 0)),
                    }
                    for b in bars
                ]
            )
    if df is None or getattr(df, "empty", True):
        n = getattr(series, "bar_count", 0)
        if not n:
            return CommandResult(success=False, error=f"No history data for {symbol}")
        # bar_count only — print count
        console.print(f"[green]{n} candles for {normalize_symbol(symbol)}[/green]")
        return CommandResult(success=True, data={"symbol": symbol, "candles": n})
    table = Table(
        title=f"History: {normalize_symbol(symbol)} (last 5 days)", header_style="bold magenta"
    )
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
    expiry = parse_flag(args, "--expiry")
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
