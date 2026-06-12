"""Main CLI/TUI entrypoint for TradeXV2 diagnostic terminal."""

from __future__ import annotations

import sys

from rich.console import Console

from brokers.gateway import Gateway
from cli.commands import (
    account as cmd_account,
)

# CLI Commands Imports
from cli.commands import (
    broker as cmd_broker,
)
from cli.commands import (
    doctor as cmd_doctor,
)
from cli.commands import (
    events as cmd_events,
)
from cli.commands import (
    instrument as cmd_instrument,
)
from cli.commands import (
    instruments as cmd_instruments,
)
from cli.commands import (
    load_test as cmd_load_test,
)
from cli.commands import (
    market as cmd_market,
)
from cli.commands import (
    oms as cmd_oms,
)
from cli.commands import (
    portfolio as cmd_portfolio,
)
from cli.commands import (
    search as cmd_search,
)
from cli.commands import (
    websocket as cmd_websocket,
)
from cli.services.broker_service import BrokerService
from cli.services.event_bus_service import EventBusService
from cli.services.oms_service import OmsService
from cli.views.tui_app import TradexTuiApp


def main() -> None:
    """Parse CLI arguments and route to commands or TUI."""
    # 1. Initialize services
    broker_service = BrokerService()
    oms_service = OmsService(broker_service)
    event_bus_service = EventBusService()

    console = Console()

    # 2. Parse basic arguments
    args = sys.argv[1:]

    if not args:
        # Launch TUI Dashboard
        app = TradexTuiApp(
            broker_service=broker_service,
            oms_service=oms_service,
            event_bus_service=event_bus_service,
        )
        app.run()
        return

    subcommand = args[0].lower()
    cmd_args = args[1:]

    # Create Gateway for market data commands (handles symbol resolution)
    _gw = None

    def _get_gateway() -> Gateway:
        nonlocal _gw
        if _gw is None:
            _gw = Gateway(broker=broker_service.active_broker, auto_connect=False)
        return _gw

    # 3. Subcommand routing
    if subcommand == "broker":
        cmd_broker.run(cmd_args, broker_service, console)

    elif subcommand == "account" or subcommand == "funds":
        cmd_account.run(cmd_args, broker_service, console)

    elif subcommand == "holdings":
        cmd_portfolio.show_holdings(broker_service, console)

    elif subcommand == "positions":
        cmd_portfolio.show_positions(broker_service, console)

    elif subcommand == "orders":
        status_filter = cmd_args[0] if cmd_args else None
        cmd_oms.show_orders(oms_service, console, status_filter)

    elif subcommand == "trades":
        cmd_oms.show_trades(oms_service, console)

    elif subcommand == "oms":
        cmd_oms.show_oms_summary(oms_service, console)

    elif subcommand == "quote":
        if not cmd_args:
            console.print("[yellow]Usage: tradex quote <symbol> [--live][/yellow]")
            return
        symbol = cmd_args[0]
        try:
            gw = _get_gateway()
            df = gw.quote(symbol)
            if df is not None and not df.empty:
                from rich.table import Table

                row = df.iloc[0]
                table = Table(title=f"Quote: {symbol.upper()}", header_style="bold green")
                table.add_column("Metric", style="bold white")
                table.add_column("Value", justify="right")
                table.add_row("LTP", f"₹{row.get('ltp', 0):,.2f}")
                table.add_row("Bid", f"₹{row.get('bid', 0):,.2f}")
                table.add_row("Ask", f"₹{row.get('ask', 0):,.2f}")
                table.add_row("Volume", f"{int(row.get('volume', 0)):,}")
                table.add_row("OI", f"{int(row.get('oi', 0)):,}")
                console.print(table)
            else:
                console.print(f"[red]No quote data for {symbol}[/red]")
        except Exception as exc:
            console.print(f"[red]Error fetching quote for {symbol}: {exc}[/red]")

    elif subcommand == "depth":
        if not cmd_args:
            console.print("[yellow]Usage: tradex depth <symbol> [--live][/yellow]")
            return
        symbol = cmd_args[0]
        try:
            gw = _get_gateway()
            df = gw.depth(symbol, levels=5)
            if df is not None and not df.empty:
                from rich.table import Table

                row = df.iloc[0]
                table = Table(title=f"Market Depth: {symbol.upper()}", header_style="bold magenta")
                table.add_column("Bid Qty", style="green", justify="right")
                table.add_column("Bid Price", style="bold green", justify="right")
                table.add_column("Ask Price", style="bold red", justify="right")
                table.add_column("Ask Qty", style="red", justify="right")
                for i in range(1, 6):
                    table.add_row(
                        f"{int(row.get(f'bid_qty_{i}', 0)):,}",
                        f"₹{row.get(f'bid_price_{i}', 0):,.2f}",
                        f"₹{row.get(f'ask_price_{i}', 0):,.2f}",
                        f"{int(row.get(f'ask_qty_{i}', 0)):,}",
                    )
                console.print(table)
            else:
                console.print(f"[red]No depth data for {symbol}[/red]")
        except Exception as exc:
            console.print(f"[red]Error fetching depth for {symbol}: {exc}[/red]")

    elif subcommand == "option-chain":
        if not cmd_args:
            console.print("[yellow]Usage: tradex option-chain <symbol> [--expiry <date>][/yellow]")
            return
        symbol = cmd_args[0]
        expiry = None
        if "--expiry" in cmd_args:
            idx = cmd_args.index("--expiry")
            if idx + 1 < len(cmd_args):
                expiry = cmd_args[idx + 1]
        try:
            cmd_market.show_option_chain(broker_service.active_broker, symbol, console, expiry)
        except Exception as exc:
            console.print(f"[red]Error fetching option-chain for {symbol}: {exc}[/red]")

    elif subcommand == "futures":
        if not cmd_args:
            console.print("[yellow]Usage: tradex futures <symbol>[/yellow]")
            return
        symbol = cmd_args[0]
        try:
            cmd_market.show_futures(broker_service.active_broker, symbol, console)
        except Exception as exc:
            console.print(f"[red]Error fetching futures for {symbol}: {exc}[/red]")

    elif subcommand == "historical" or subcommand == "history":
        if not cmd_args:
            console.print("[yellow]Usage: tradex history <symbol>[/yellow]")
            return
        symbol = cmd_args[0]
        try:
            gw = _get_gateway()
            df = gw.history(symbol, timeframe="1d", lookback_days=10)
            if df is not None and not df.empty:
                from rich.table import Table

                table = Table(
                    title=f"History: {symbol.upper()} (last 5 days)",
                    header_style="bold magenta",
                )
                table.add_column("Date", style="bold white")
                table.add_column("Open", justify="right")
                table.add_column("High", justify="right")
                table.add_column("Low", justify="right")
                table.add_column("Close", justify="right")
                table.add_column("Volume", justify="right")
                for _, row in df.tail(5).iterrows():
                    ts = row["timestamp"]
                    date_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)
                    table.add_row(
                        date_str,
                        f"₹{row['open']:,.2f}",
                        f"₹{row['high']:,.2f}",
                        f"₹{row['low']:,.2f}",
                        f"₹{row['close']:,.2f}",
                        f"{int(row['volume']):,}",
                    )
                console.print(table)
                console.print(f"[dim]{len(df)} candles total[/dim]")
            else:
                console.print(f"[red]No history data for {symbol}[/red]")
        except Exception as exc:
            console.print(f"[red]Error fetching history for {symbol}: {exc}[/red]")

    elif subcommand == "stream":
        if not cmd_args:
            console.print("[yellow]Usage: tradex stream <symbol>[/yellow]")
            return
        symbol = cmd_args[0]
        try:
            cmd_market.show_stream(broker_service.active_broker, symbol, console)
        except Exception as exc:
            console.print(f"[red]Error streaming {symbol}: {exc}[/red]")

    elif subcommand == "websocket":
        cmd_websocket.run(cmd_args, broker_service, console)

    elif subcommand == "events":
        cmd_events.run(cmd_args, event_bus_service, console)

    elif subcommand == "search":
        cmd_search.run(cmd_args, broker_service.active_broker, console)

    elif subcommand == "instrument":
        cmd_instrument.run(cmd_args, broker_service.active_broker, console)

    elif subcommand == "instruments":
        cmd_instruments.run(cmd_args, console)

    elif subcommand == "doctor":
        cmd_doctor.run(cmd_args, broker_service, console)

    elif subcommand == "load-test":
        cmd_load_test.run(cmd_args, broker_service, console)

    else:
        console.print(f"[red]Error: Unknown command '{subcommand}'[/red]")
        console.print(
            "[yellow]Available commands: broker, account/funds, holdings, positions, orders, trades, oms, quote, depth, option-chain, futures, historical/history, stream, websocket, events, search, instrument, instruments, doctor, load-test[/yellow]"
        )


if __name__ == "__main__":
    main()
