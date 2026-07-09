"""Main CLI/TUI entrypoint for TradeXV2 diagnostic terminal."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from rich.console import Console

# Initialize centralized logging BEFORE any other imports that log
from infrastructure.logging_config import configure_logging
configure_logging()

logger = logging.getLogger(__name__)

# Load environment variables once at startup so every subcommand sees them.
_ENV_PATH = Path(".env.local")
if _ENV_PATH.exists() and _ENV_PATH.stat().st_size > 0:
    load_dotenv(_ENV_PATH, override=True)

from cli.commands import (
    account as cmd_account,
    analytics as cmd_analytics,
    benchmark as cmd_benchmark,
    broker as cmd_broker,
    compare as cmd_compare,
    dashboard as cmd_dashboard,
    doctor as cmd_doctor,
    events as cmd_events,
    instrument_info as cmd_instrument_info,
    instrument as cmd_instrument,
    instruments as cmd_instruments,
    journal as cmd_journal,
    load_test as cmd_load_test,
    market as cmd_market,
    news as cmd_news,
    oms as cmd_oms,
    order_placement as cmd_order_placement,
    order_composition as cmd_order_composition,
    risk_controls as cmd_risk_controls,
    cache_management as cmd_cache_management,
    portfolio as cmd_portfolio,
    quality_report as cmd_quality_report,
    search as cmd_search,
    validate as cmd_validate,
    validate_history as cmd_validate_history,
    validate_option_chain as cmd_validate_option_chain,
    options_sync as cmd_options_sync,
    views as cmd_views,
    websocket as cmd_websocket,
)
from cli.commands.registry import lookup_handler, register_handler
from cli.services.broker_registry import create_gateway
from cli.services.broker_service import BrokerService
from cli.services.event_bus_service import EventBusService

# ── Command registry (single source of truth for CLI dispatch) ───────────
# Every top-level command in cli/tests/endpoint_manifest.TOP_LEVEL_COMMANDS
# is registered here via register_handler(name, fn). The explicit branches in
# main() route the common commands; this table is the canonical registry
# (consumed by test_command_registry.py and the fallback dispatch below) and
# backs any command not covered by an explicit branch.
COMMAND_HANDLERS = {
    "broker": cmd_broker.run,
    "dashboard": cmd_dashboard.run,
    "validate": cmd_validate.run,
    "validate-history": cmd_validate_history.run,
    "validate-option-chain": cmd_validate_option_chain.run,
    "options-sync": cmd_options_sync.run_options_sync,
    "benchmark": cmd_benchmark.run,
    "compare": cmd_compare.run,
    "quality-report": cmd_quality_report.run,
    "instrument-info": cmd_instrument_info.run,
    "account": cmd_account.run,
    "funds": cmd_account.run,
    "holdings": cmd_portfolio.show_holdings,
    "positions": cmd_portfolio.show_positions,
    "orders": cmd_oms.show_orders,
    "trades": cmd_oms.show_trades,
    "oms": cmd_oms.show_oms_summary,
    "quote": cmd_market.run,
    "depth": cmd_market.run,
    "option-chain": cmd_market.run,
    "futures": cmd_market.run,
    "historical": cmd_market.run,
    "history": cmd_market.run,
    "stream": cmd_market.run,
    "websocket": cmd_websocket.run,
    "journal": cmd_journal.run_journal,
    "events": cmd_events.run,
    "search": cmd_search.run,
    "instrument": cmd_instrument.run,
    "instruments": cmd_instruments.run,
    "doctor": cmd_doctor.run,
    "load-test": cmd_load_test.run,
    "news": cmd_news.run,
    "analytics": cmd_analytics.run,
    "views": cmd_views.run_views,
    "place-order": cmd_order_placement.place_order,
    "cancel-order": cmd_order_placement.cancel_order,
    "modify-order": cmd_order_placement.modify_order,
    "place-orders": cmd_order_placement.place_orders_batch,
    "bracket-order": cmd_order_composition.place_bracket_order,
    "oco-order": cmd_order_composition.place_oco_order,
    "basket-order": cmd_order_composition.place_basket_order,
    "risk": cmd_risk_controls.run,
    "cache": cmd_cache_management.run,
}
for _name, _fn in COMMAND_HANDLERS.items():
    register_handler(_name, _fn)


def _try_create_gateway(
    broker: str = "dhan",
    load_instruments: bool = True,
    event_bus: Any | None = None,
    lifecycle: Any | None = None,
) -> Any:
    """Attempt to create a BrokerGateway; return None on failure.

    Delegates to the unified :func:`cli.services.broker_registry.create_gateway`.
    """
    try:
        return create_gateway(
            broker=broker,
            load_instruments=load_instruments,
            event_bus=event_bus,
            lifecycle=lifecycle,
        )
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

    # --risk-fail-open: explicit operator consent to use the legacy 1,000,000
    # INR placeholder capital when the real broker balance is unavailable.
    # This flag MUST be set explicitly; setting RISK_FAIL_OPEN=1 in the
    # environment without this flag is refused at startup (see
    # ``BrokerService.__init__``).
    authorize_risk_fail_open = "--risk-fail-open" in args
    if authorize_risk_fail_open:
        args = [a for a in args if a != "--risk-fail-open"]

    console = Console()

    if not args or args[0] in ("--help", "-h", "help"):
        console.print("[bold]TradeXV2 CLI[/bold]\n")
        console.print("[yellow]Usage: tradex <command> [args] [--broker dhan|upstox] [--risk-fail-open][/yellow]\n")
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
            ("options-sync", "Sync option data from Trade_J DuckDB (daily cron)"),
        ]
        for cmd, desc in cmds:
            console.print(f"  [cyan]{cmd:<25}[/cyan] {desc}")
        console.print("\n[dim]Examples:[/dim]")
        console.print("  tradex analytics scan-momentum --file universe.csv --limit 5")
        console.print("  tradex analytics backtest --file ohlcv.csv --capital 100000")
        console.print("  tradex validate data nifty500.csv --timeframe 1d")
        return

    subcommand = args[0].lower()
    cmd_args = args[1:]

    # Commands that don't need a broker gateway
    _NO_GATEWAY_CMDS = {"help", "journal", "views", "validate"}

    # Commands that need instruments (historical, search, instruments)
    _NEEDS_INSTRUMENTS = {"historical", "history", "search", "instrument", "instruments", "option-chain", "futures"}

    # Lazy gateway accessor for market data commands
    gateway = None
    broker_service = BrokerService(authorize_risk_fail_open=authorize_risk_fail_open)
    # Phase 3: build EventBusService WITHOUT an event bus so it does not
    # create a second, separate EventBus. We re-attach below once the
    # OMS TradingContext is available so the service mirrors the canonical
    # bus. Until then ``events`` will print an explanatory banner.
    event_bus_service = EventBusService()

    _gw: Any = None

    def _get_gateway() -> Any:
        nonlocal _gw
        if _gw is None:
            # Only load instruments for commands that need them
            load_inst = subcommand in _NEEDS_INSTRUMENTS
            _gw = _try_create_gateway(broker_name, load_instruments=load_inst)
        return _gw

    # Skip gateway creation for commands that don't need it
    if subcommand not in _NO_GATEWAY_CMDS:
        # Only load instruments for commands that need them
        load_inst = subcommand in _NEEDS_INSTRUMENTS
        gateway = _try_create_gateway(
            broker_name,
            load_instruments=load_inst,
            event_bus=event_bus_service.event_bus,
            lifecycle=broker_service.lifecycle,
        )
        _gw = gateway

    # Wire TradingContext / EventBus for live gateway commands.
    # (D6: OmsService retired — BrokerService now owns the live_actionable
    # guard + order/trade read access; no separate OMS service object needed.)
    tc = None
    if subcommand not in _NO_GATEWAY_CMDS:
        tc = broker_service.trading_context
        # Phase 3: re-bind EventBusService to the canonical OMS bus so the
        # CLI ``events`` command mirrors real OMS activity instead of
        # fabricating events on a separate bus.
        if tc is not None:
            event_bus_service = EventBusService(event_bus=tc.event_bus)

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
                if gw is None:
                    console.print(f"[red]No {broker_name} gateway available. Check credentials.[/red]")
                    return
                quote = gw.quote(symbol)
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
                if gw is None:
                    console.print(f"[red]No {broker_name} gateway available. Check credentials.[/red]")
                    return
                depth = gw.depth(symbol)
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
                if gw is None:
                    console.print(f"[red]No {broker_name} gateway available. Check credentials.[/red]")
                    return
                to_date = date.today()
                from_date = to_date - timedelta(days=10)
                df = gw.historical.history(
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

        elif subcommand == "options-sync":
            cmd_options_sync.run_options_sync(cmd_args, console)

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
            # Fallback: route any command present in the canonical registry
            # but not covered by an explicit branch above (order/risk/cache,
            # validate-* aliases, instrument-info, ...).
            try:
                handler = lookup_handler(subcommand)
            except KeyError:
                handler = None
            if handler is not None:
                try:
                    handler(cmd_args, broker_service, console)
                except TypeError:
                    console.print(
                        f"[red]Error: command '{subcommand}' is misconfigured[/red]"
                    )
            else:
                console.print(f"[red]Error: Unknown command '{subcommand}'[/red]")
                console.print(
                    "[yellow]Available commands: broker, analytics, account/funds, holdings, positions, orders, trades, oms, quote, depth, option-chain, futures, historical/history, stream, websocket, events, search, instrument, instruments, doctor, load-test, news[/yellow]"
                )
    finally:
        broker_service.close()
        if gateway is not None:
            try:
                gateway.close()
            except Exception as exc:
                logger.debug("gateway_close_failed: %s", exc)


if __name__ == "__main__":
    main()
