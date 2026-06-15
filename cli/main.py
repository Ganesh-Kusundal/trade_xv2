"""Main CLI/TUI entrypoint for TradeXV2 diagnostic terminal."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from rich.console import Console

# Load environment variables once at startup so every subcommand sees them.
_ENV_PATH = Path(".env.local")
if _ENV_PATH.exists() and _ENV_PATH.stat().st_size > 0:
    load_dotenv(_ENV_PATH, override=True)

from brokers.dhan import BrokerGateway, BrokerFactory
from cli.commands import (
    account as cmd_account,
)
from cli.commands import (
    analytics as cmd_analytics,
)

# CLI Commands Imports
from cli.commands import (
    broker as cmd_broker,
)
from cli.commands import (
    news as cmd_news,
)
from cli.commands import (
    validate as cmd_validate,
)
from cli.commands import (
    benchmark as cmd_benchmark,
)
from cli.commands import (
    dashboard as cmd_dashboard,
)
from cli.commands import (
    compare as cmd_compare,
)
from cli.commands import (
    validate_history as cmd_validate_history,
)
from cli.commands import (
    validate_option_chain as cmd_validate_option_chain,
)
from cli.commands import (
    quality_report as cmd_quality_report,
)
from cli.commands import (
    instrument_info as cmd_instrument_info,
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
from cli.commands import (
    journal as cmd_journal,
)
from cli.commands import (
    views as cmd_views,
)
from cli.services.broker_service import BrokerService
from cli.services.event_bus_service import EventBusService
from cli.services.oms_service import OmsService
from cli.views.tui_app import TradexTuiApp


def _try_create_gateway(broker: str = "dhan") -> Any:
    """Attempt to create a BrokerGateway; return None on failure."""
    if broker == "upstox":
        env_path = Path(".env.upstox")
        if not env_path.exists():
            return None
        try:
            from brokers.upstox.factory import UpstoxBrokerFactory
            return UpstoxBrokerFactory.create(env_path=env_path, load_instruments=True)
        except Exception:
            return None
    else:
        env_path = Path(".env.local")
        if not env_path.exists():
            return None
        try:
            return BrokerFactory.create(env_path=env_path, load_instruments=True)
        except Exception:
            return None


def main() -> None:
    """Parse CLI arguments and route to commands or TUI."""
    args = sys.argv[1:]

    broker_name = "dhan"
    if "--broker" in args:
        idx = args.index("--broker")
        if idx + 1 < len(args):
            broker_name = args[idx + 1].lower()
            args = args[:idx] + args[idx + 2:]

    console = Console()

    if not args or args[0] in ("--help", "-h", "help"):
        console.print("[bold]TradeXV2 CLI[/bold]\n")
        console.print("[yellow]Usage: tradex <command> [args] [--broker dhan|upstox][/yellow]\n")
        console.print("[bold]Commands:[/bold]")
        cmds = [
            ("broker", "Show broker connection info"),
            ("analytics", "Run analytics (scan, rank, backtest, paper, sectors)"),
            ("validate", "Validate data (broker health or CSV file)"),
            ("benchmark", "Benchmark broker latency"),
            ("account/funds", "Show account balance"),
            ("holdings", "Show holdings"),
            ("positions", "Show positions"),
            ("orders", "Show orders"),
            ("trades", "Show trades"),
            ("oms", "Order management summary"),
            ("quote", "Get quote for a symbol"),
            ("depth", "Get market depth"),
            ("option-chain", "Get option chain"),
            ("futures", "Get futures chain"),
            ("historical/history", "Get historical data"),
            ("stream", "Stream live data"),
            ("websocket", "WebSocket connection"),
            ("events", "Event bus"),
            ("search", "Search instruments"),
            ("instrument", "Instrument info"),
            ("instruments", "List instruments"),
            ("doctor", "System diagnostics"),
            ("load-test", "Load test broker"),
            ("news", "Market news"),
            ("journal", "Trade journal (record, close, list, summary)"),
            ("views", "DuckDB analytics view management"),
        ]
        for cmd, desc in cmds:
            console.print(f"  [cyan]{cmd:<25}[/cyan] {desc}")
        console.print(f"\n[dim]Examples:[/dim]")
        console.print(f"  tradex analytics scan-momentum --file universe.csv --limit 5")
        console.print(f"  tradex analytics backtest --file ohlcv.csv --capital 100000")
        console.print(f"  tradex validate data nifty500.csv --timeframe 1d")
        return

    subcommand = args[0].lower()
    cmd_args = args[1:]

    # Commands that don't need a broker gateway
    _NO_GATEWAY_CMDS = {"help", "journal", "views"}

    # Lazy gateway accessor for market data commands
    gateway = None
    broker_service = BrokerService()
    event_bus_service = EventBusService()

    _gw: Any = None

    def _get_gateway() -> Any:
        nonlocal _gw
        if _gw is None:
            _gw = _try_create_gateway(broker_name)
        return _gw

    # Skip gateway creation for commands that don't need it
    if subcommand not in _NO_GATEWAY_CMDS:
        gateway = _try_create_gateway(broker_name)
        _gw = gateway

    # Wire TradingContext into OmsService when available
    tc = broker_service.trading_context
    oms_service = OmsService(gateway=gateway, trading_context=tc)

    # 3. Subcommand routing
    try:
        if subcommand == "broker":
            cmd_broker.run(cmd_args, broker_service, console)

        elif subcommand == "dashboard":
            cmd_dashboard.run(cmd_args, broker_service, console)

    elif subcommand == "validate":
        if cmd_args and cmd_args[0] == "history":
            cmd_validate_history.run(cmd_args[1:], broker_service, console)
        elif cmd_args and cmd_args[0] == "option-chain":
            cmd_validate_option_chain.run(cmd_args[1:], broker_service, console)
        else:
            cmd_validate.run(cmd_args, broker_service, console)

    elif subcommand == "benchmark":
        cmd_benchmark.run(cmd_args, broker_service, console)

    elif subcommand == "analytics":
        cmd_analytics.run(cmd_args, broker_service, console)

    elif subcommand == "compare":
        cmd_compare.run(cmd_args, broker_service, console)

    elif subcommand == "quality-report":
        cmd_quality_report.run(cmd_args, broker_service, console)

    elif subcommand == "instrument":
        cmd_instrument_info.run(cmd_args, broker_service, console)

    elif subcommand == "account" or subcommand == "funds":
        cmd_account.run(cmd_args, broker_service, console)

    elif subcommand == "holdings":
        cmd_portfolio.show_holdings(broker_service, console)

    elif subcommand == "positions":
        cmd_portfolio.show_positions(broker_service, console)

    elif subcommand == "orders":
        status_filter = cmd_args[0] if cmd_args else None
        cmd_oms.show_orders(broker_service, console, status_filter)

    elif subcommand == "trades":
        cmd_oms.show_trades(broker_service, console)

    elif subcommand == "oms":
        cmd_oms.show_oms_summary(broker_service, console)

    elif subcommand == "quote":
        if not cmd_args:
            console.print("[yellow]Usage: tradex quote <symbol> [--live][/yellow]")
            return
        symbol = cmd_args[0]
        try:
            gw = _get_gateway()
            quote = gw.market_data.get_quote(symbol)
            if quote is not None:
                from rich.table import Table

                table = Table(title=f"Quote: {symbol.upper()}", header_style="bold green")
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
            depth = gw.market_data.get_depth(symbol)
            if depth is not None and (depth.bids or depth.asks):
                from rich.table import Table

                table = Table(title=f"Market Depth: {symbol.upper()}", header_style="bold magenta")
                table.add_column("Bid Qty", style="green", justify="right")
                table.add_column("Bid Price", style="bold green", justify="right")
                table.add_column("Ask Price", style="bold red", justify="right")
                table.add_column("Ask Qty", style="red", justify="right")
                levels = max(len(depth.bids), len(depth.asks))
                for i in range(levels):
                    bid = depth.bids[i] if i < len(depth.bids) else None
                    ask = depth.asks[i] if i < len(depth.asks) else None
                    table.add_row(
                        f"{bid.quantity:,}" if bid else "-",
                        f"\u20b9{bid.price:,.2f}" if bid else "-",
                        f"\u20b9{ask.price:,.2f}" if ask else "-",
                        f"{ask.quantity:,}" if ask else "-",
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
            cmd_market.show_option_chain(broker_service, symbol, console, expiry)
        except Exception as exc:
            console.print(f"[red]Error fetching option-chain for {symbol}: {exc}[/red]")

    elif subcommand == "futures":
        if not cmd_args:
            console.print("[yellow]Usage: tradex futures <symbol>[/yellow]")
            return
        symbol = cmd_args[0]
        try:
            cmd_market.show_futures(broker_service, symbol, console)
        except Exception as exc:
            console.print(f"[red]Error fetching futures for {symbol}: {exc}[/red]")

    elif subcommand == "historical" or subcommand == "history":
        if not cmd_args:
            console.print("[yellow]Usage: tradex history <symbol>[/yellow]")
            return
        symbol = cmd_args[0]
        try:
            from datetime import date, timedelta

            gw = _get_gateway()
            to_date = date.today()
            from_date = to_date - timedelta(days=10)
            df = gw.historical.get_historical(
                symbol, "NSE",
                from_date=from_date.strftime("%Y-%m-%d"),
                to_date=to_date.strftime("%Y-%m-%d"),
                timeframe="1D",
            )
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
                        f"\u20b9{row['open']:,.2f}",
                        f"\u20b9{row['high']:,.2f}",
                        f"\u20b9{row['low']:,.2f}",
                        f"\u20b9{row['close']:,.2f}",
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
            cmd_market.show_stream(broker_service, symbol, console)
        except Exception as exc:
            console.print(f"[red]Error streaming {symbol}: {exc}[/red]")

    elif subcommand == "websocket":
        cmd_websocket.run(cmd_args, broker_service, console)

    elif subcommand == "journal":
        cmd_journal.run_journal(cmd_args, console)

    elif subcommand == "views":
        cmd_views.run_views(cmd_args, console)

    elif subcommand == "events":
        cmd_events.run(cmd_args, event_bus_service, console)

    elif subcommand == "search":
        cmd_search.run(cmd_args, broker_service, console)

    elif subcommand == "instruments":
        cmd_instruments.run(cmd_args, broker_service, console)

    elif subcommand == "doctor":
        cmd_doctor.run(cmd_args, broker_service, console)

    elif subcommand == "load-test":
        cmd_load_test.run(cmd_args, broker_service, console)

    elif subcommand == "news":
        cmd_news.run(cmd_args, broker_service, console)

    else:
            console.print(f"[red]Error: Unknown command '{subcommand}'[/red]")
            console.print(
                "[yellow]Available commands: broker, analytics, account/funds, holdings, positions, orders, trades, oms, quote, depth, option-chain, futures, historical/history, stream, websocket, events, search, instrument, instruments, doctor, load-test, news[/yellow]"
            )
    finally:
        broker_service.close()


if __name__ == "__main__":
    main()
