"""Main CLI/TUI entrypoint for TradeXV2 diagnostic terminal.

I-10 / I-14 / P0-10 (2026-06-17): dict-based dispatch, single
composition root via BrokerService, proper exit codes, and --json
output mode.
"""

from __future__ import annotations

import json as _json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

# Initialize centralized logging BEFORE any other imports that log
from brokers.common.logging_config import setup_logging
from brokers.common.env_loader import load_env_file
from brokers.common.core.domain import DepthLevel, MarketDepth
setup_logging()

logger = logging.getLogger(__name__)

# Load environment variables once at startup so every subcommand sees them.
_ENV_PATH = Path(".env.local")
if _ENV_PATH.exists() and _ENV_PATH.stat().st_size > 0:
    load_env_file(_ENV_PATH)

from cli.commands import (
    account as cmd_account,
    analytics as cmd_analytics,
    benchmark as cmd_benchmark,
    broker as cmd_broker,
    cache_management as cmd_cache_management,
    compare as cmd_compare,
    dashboard as cmd_dashboard,
    doctor as cmd_doctor,
    events as cmd_events,
    instrument_info as cmd_instrument_info,
    instruments as cmd_instruments,
    journal as cmd_journal,
    load_test as cmd_load_test,
    market as cmd_market,
    news as cmd_news,
    oms as cmd_oms,
    options_sync as cmd_options_sync,
    order_composition as cmd_order_composition,
    order_placement as cmd_order_placement,
    portfolio as cmd_portfolio,
    quality_report as cmd_quality_report,
    risk_controls as cmd_risk_controls,
    search as cmd_search,
    validate as cmd_validate,
    validate_history as cmd_validate_history,
    validate_option_chain as cmd_validate_option_chain,
    views as cmd_views,
    websocket as cmd_websocket,
)
from cli.commands.registry import (
    DISPATCH_TABLE,
    CommandResult,
    lookup_handler,
    register_handler,
)
from cli.commands.registry import register as _register_cmd
from cli.services.broker_service import BrokerService
from cli.services.event_bus_service import EventBusService

# ── Module-path registry (discoverability, kept for tests) ─────────────────
_register_cmd("broker", "cli.commands.broker")
_register_cmd("dashboard", "cli.commands.dashboard")
_register_cmd("validate", "cli.commands.validate")
_register_cmd("validate-history", "cli.commands.validate_history")
_register_cmd("validate-option-chain", "cli.commands.validate_option_chain")
_register_cmd("options-sync", "cli.commands.options_sync")
_register_cmd("benchmark", "cli.commands.benchmark")
_register_cmd("compare", "cli.commands.compare")
_register_cmd("quality-report", "cli.commands.quality_report")
_register_cmd("instrument-info", "cli.commands.instrument_info")
_register_cmd("account", "cli.commands.account")
_register_cmd("holdings", "cli.commands.portfolio")
_register_cmd("positions", "cli.commands.portfolio")
_register_cmd("orders", "cli.commands.oms")
_register_cmd("trades", "cli.commands.oms")
_register_cmd("oms", "cli.commands.oms")
_register_cmd("quote", "cli.commands.market")
_register_cmd("depth", "cli.commands.market")
_register_cmd("option-chain", "cli.commands.market")
_register_cmd("futures", "cli.commands.market")
_register_cmd("historical", "cli.commands.market")
_register_cmd("history", "cli.commands.market")
_register_cmd("stream", "cli.commands.market")
_register_cmd("websocket", "cli.commands.websocket")
_register_cmd("journal", "cli.commands.journal")
_register_cmd("events", "cli.commands.events")
_register_cmd("search", "cli.commands.search")
_register_cmd("instrument", "cli.commands.instrument")
_register_cmd("instruments", "cli.commands.instruments")
_register_cmd("funds", "cli.commands.account")
_register_cmd("doctor", "cli.commands.doctor")
_register_cmd("load-test", "cli.commands.load_test")
_register_cmd("news", "cli.commands.news")
_register_cmd("analytics", "cli.commands.analytics")
_register_cmd("views", "cli.commands.views")
_register_cmd("place-order", "cli.commands.order_placement")
_register_cmd("cancel-order", "cli.commands.order_placement")
_register_cmd("modify-order", "cli.commands.order_placement")
_register_cmd("place-orders", "cli.commands.order_placement")
_register_cmd("bracket-order", "cli.commands.order_composition")
_register_cmd("oco-order", "cli.commands.order_composition")
_register_cmd("basket-order", "cli.commands.order_composition")
_register_cmd("risk", "cli.commands.risk_controls")
_register_cmd("cache", "cli.commands.cache_management")


# ── Helpers ─────────────────────────────────────────────────────────────────

def _print_help(console: Console) -> None:
    console.print("[bold]TradeXV2 CLI[/bold]\n")
    console.print("[yellow]Usage: tradex <command> [args] [--broker dhan|upstox] [--json] [--verbose] [--timing][/yellow]\n")
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
        ("place-order", "Place a new order"),
        ("cancel-order", "Cancel an existing order"),
        ("modify-order", "Modify order price/quantity"),
        ("place-orders", "Batch order placement from CSV"),
        ("bracket-order", "Bracket order (entry + target + SL)"),
        ("oco-order", "One-Cancels-Other order"),
        ("basket-order", "Multi-symbol basket order"),
        ("risk", "Risk management controls"),
        ("cache", "Instrument cache management"),
    ]
    for cmd, desc in cmds:
        console.print(f"  [cyan]{cmd:<25}[/cyan] {desc}")
    console.print("\n[bold]Flags:[/bold]")
    console.print("  [cyan]--broker NAME[/cyan]       Use specific broker (default: dhan)")
    console.print("  [cyan]--json[/cyan]              Output results as JSON")
    console.print("  [cyan]--verbose[/cyan]           Enable debug logging")
    console.print("  [cyan]--timing[/cyan]            Show command execution time")
    console.print("\n[dim]Examples:[/dim]")
    console.print("  tradex analytics scan-momentum --file universe.csv --limit 5")
    console.print("  tradex analytics backtest --file ohlcv.csv --capital 100000")
    console.print("  tradex validate data nifty500.csv --timeframe 1d")
    console.print("  tradex place-order RELIANCE BUY 10 --type MARKET")
    console.print("  tradex doctor --parallel --timing")
    console.print("  tradex quote RELIANCE --verbose --timing")


# ── Inline / wrapped command handlers ──────────────────────────────────────
# Commands whose logic lives inline (quote, depth, historical, option-chain,
# futures, stream) or that need signature adaptation are wrapped here rather
# than in separate modules.  Every handler returns CommandResult | None for
# unified exit-code handling.


def _handle_quote(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult | None:
    if not args:
        console.print("[yellow]Usage: tradex quote <symbol>[/yellow]")
        return CommandResult(success=False, error="Missing symbol")
    symbol = args[0]
    gw = broker_service.active_broker
    if gw is None:
        return CommandResult(success=False, error=f"No broker gateway available. Check credentials.")
    quote = gw.quote(symbol)
    if quote is None:
        return CommandResult(success=False, error=f"No quote data for {symbol}")
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
    return CommandResult(success=True, data={
        "symbol": symbol, "ltp": str(quote.ltp), "open": str(quote.open),
        "high": str(quote.high), "low": str(quote.low), "close": str(quote.close),
        "volume": quote.volume, "change": str(quote.change),
    })


def _handle_depth(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult | None:
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
    table = Table(title=f"Market Depth: {symbol.upper()}", header_style="bold magenta")
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


def _handle_history(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult | None:
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
    # Prefer the broker-specific `.historical` adapter (e.g. Dhan) for
    # retries/caching; fall back to the MarketDataGateway.history() ABC
    # method when no adapter is exposed.
    history_fn: Any = getattr(getattr(gw, "historical", None), "history", gw.history)
    to_date = date.today()
    from_date = to_date - timedelta(days=10)
    df = history_fn(
        symbol, "NSE",
        from_date=from_date.strftime("%Y-%m-%d"),
        to_date=to_date.strftime("%Y-%m-%d"),
        timeframe="1D",
    )
    if df is None or df.empty:
        return CommandResult(success=False, error=f"No history data for {symbol}")
    table = Table(title=f"History: {symbol.upper()} (last 5 days)", header_style="bold magenta")
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


def _handle_option_chain(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult | None:
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


def _handle_futures(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult | None:
    if not args:
        console.print("[yellow]Usage: tradex futures <symbol>[/yellow]")
        return CommandResult(success=False, error="Missing symbol")
    symbol = args[0]
    cmd_market.show_futures(broker_service, symbol, console)
    return CommandResult(success=True)


def _handle_stream(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult | None:
    if not args:
        console.print("[yellow]Usage: tradex stream <symbol>[/yellow]")
        return CommandResult(success=False, error="Missing symbol")
    symbol = args[0]
    cmd_market.show_stream(broker_service, symbol, console)
    return CommandResult(success=True)


def _handle_orders(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult | None:
    status_filter = args[0] if args else None
    cmd_oms.show_orders(broker_service, console, status_filter)
    return CommandResult(success=True)


def _handle_validate(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult | None:
    if args and args[0] == "history":
        cmd_validate_history.run(args[1:], broker_service, console)
    elif args and args[0] == "option-chain":
        cmd_validate_option_chain.run(args[1:], broker_service, console)
    else:
        cmd_validate.run(args, broker_service, console)
    return CommandResult(success=True)# ── Dispatch table (P0-10: replaces hand-rolled if/elif) ───────────────────
# Standard signature: (args, broker_service, console) → CommandResult | None


def _wrap(_fn: Any, *args: Any, **kwargs: Any) -> CommandResult:
    """Invoke *fn* and return a successful CommandResult.

    Adapter for commands whose native ``run`` returns ``None``; lets
    us keep a uniform ``(args, bs, console) -> CommandResult | None``
    signature in the dispatch table so mypy can type-check handlers.
    """
    _fn(*args, **kwargs)
    return CommandResult(success=True)





_DISPATCH: list[tuple[str, Any]] = [
    # Standard routing — module-level run() functions
    ("broker",            cmd_broker.run),
    ("dashboard",         cmd_dashboard.run),
    ("benchmark",         cmd_benchmark.run),
    ("analytics",         cmd_analytics.run),
    ("compare",           cmd_compare.run),
    ("quality-report",     cmd_quality_report.run),
    ("instrument",        cmd_instrument_info.run),
    ("instrument-info",   cmd_instrument_info.run),
    ("account",           cmd_account.run),
    ("funds",             cmd_account.run),
    ("search",            cmd_search.run),
    ("instruments",       cmd_instruments.run),
    ("doctor",            cmd_doctor.run),
    ("load-test",         cmd_load_test.run),
    ("news",              cmd_news.run),
    ("websocket",         cmd_websocket.run),
    ("validate-history",  cmd_validate_history.run),
    ("validate-option-chain", cmd_validate_option_chain.run),
    # Order lifecycle commands (Agent 1)
    ("place-order",       lambda a, bs, c: cmd_order_placement.place_order(a, bs, c)),
    ("cancel-order",      lambda a, bs, c: cmd_order_placement.cancel_order(a, bs, c)),
    ("modify-order",      lambda a, bs, c: cmd_order_placement.modify_order(a, bs, c)),
    ("place-orders",      lambda a, bs, c: cmd_order_placement.place_orders_batch(a, bs, c)),
    # Order composition patterns (Agent 3)
    ("bracket-order",     lambda a, bs, c: cmd_order_composition.place_bracket_order(a, bs, c)),
    ("oco-order",         lambda a, bs, c: cmd_order_composition.place_oco_order(a, bs, c)),
    ("basket-order",      lambda a, bs, c: cmd_order_composition.place_basket_order(a, bs, c)),
    # Risk management commands (Agent 2)
    ("risk",              lambda a, bs, c: cmd_risk_controls.run(a, bs, c)),
    # Cache management (Agent 4)
    ("cache",             lambda a, bs, c: cmd_cache_management.run(a, bs, c)),
    # Signature-adapted wrappers (routed through _wrap helper)
    ("holdings",          lambda a, bs, c: _wrap(cmd_portfolio.show_holdings, bs, c)),
    ("positions",         lambda a, bs, c: _wrap(cmd_portfolio.show_positions, bs, c)),
    ("trades",            lambda a, bs, c: _wrap(cmd_oms.show_trades, bs, c)),
    ("oms",               lambda a, bs, c: _wrap(cmd_oms.show_oms_summary, bs, c)),
    ("journal",           lambda a, bs, c: _wrap(cmd_journal.run_journal, a, c)),
    ("views",             lambda a, bs, c: _wrap(cmd_views.run_views, a, c)),
    ("options-sync",      lambda a, bs, c: _wrap(cmd_options_sync.run_options_sync, a, c)),
    ("events",            lambda a, bs, c: _wrap(cmd_events.run, a, EventBusService(), c)),
    # Inline handlers (gateway access routed through BrokerService)
    ("quote",             _handle_quote),
    ("depth",             _handle_depth),
    ("historical",        _handle_history),
    ("history",           _handle_history),
    ("option-chain",      _handle_option_chain),
    ("futures",           _handle_futures),
    ("stream",            _handle_stream),
    ("orders",            _handle_orders),
    ("validate",          _handle_validate),
]

# Populate the registry dispatch table
for _name, _fn in _DISPATCH:
    register_handler(_name, _fn)


# ── Main entry point ───────────────────────────────────────────────────────

# Commands that do NOT need a broker gateway at all (no BrokerService init).
_NO_GATEWAY_CMDS = frozenset({"help", "journal", "views", "options-sync"})


def _parse_flags(argv: list[str]) -> tuple[str, list[str], bool, bool, bool]:
    """Extract --broker, --json, --verbose, --timing and return (broker_name, remaining_args, json_mode, verbose, show_timing).
    
    Returns
    -------
    tuple[str, list[str], bool, bool, bool]
        (broker_name, remaining_args, json_mode, verbose, show_timing)
    
    Examples
    --------
    >>> _parse_flags(['--broker', 'upstox', '--verbose', 'doctor'])
    ('upstox', ['doctor'], False, True, False)
    >>> _parse_flags(['--timing', '--json', 'quote', 'RELIANCE'])
    ('dhan', ['quote', 'RELIANCE'], True, False, True)
    """
    broker_name = "dhan"
    json_mode = False
    verbose = False
    show_timing = False
    remaining: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--broker" and i + 1 < len(argv):
            broker_name = argv[i + 1].lower()
            i += 2
        elif a == "--json":
            json_mode = True
            i += 1
        elif a == "--verbose":
            verbose = True
            logging.getLogger().setLevel(logging.DEBUG)
            i += 1
        elif a == "--timing":
            show_timing = True
            i += 1
        else:
            remaining.append(a)
            i += 1
    return broker_name, remaining, json_mode, verbose, show_timing


def main() -> None:
    """Parse CLI arguments and route to commands or TUI.

    I-10: every path calls ``sys.exit(n)`` so the process exit code
    reflects success (0) or failure (1).

    I-14: :class:`BrokerService` is the single composition root for
    all gateway access.  No secondary gateway is created directly.

    P0-10: dict-based dispatch replaces the hand-rolled ``if/elif``
    chain.  ``--json`` flag produces structured output on stdout.
    
    Phase 5.3: Added --verbose (debug logging) and --timing (execution time) flags.
    """
    import time
    start_time = time.time()
    
    broker_name, cmd_args, json_mode, verbose, show_timing = _parse_flags(sys.argv[1:])

    console: Console
    if json_mode:
        console = Console(quiet=True, highlight=False)
    else:
        console = Console()
    
    if verbose:
        logger.debug("verbose_mode_enabled", extra={"broker": broker_name, "args": cmd_args})

    # Help / no args
    if not cmd_args or cmd_args[0] in ("--help", "-h", "help"):
        _print_help(console)
        if json_mode:
            _print_json({"help": True, "commands": list(DISPATCH_TABLE)})
        sys.exit(0)

    subcommand = cmd_args[0].lower()
    sub_args = cmd_args[1:]

    # Commands that never touch a broker gateway
    if subcommand in _NO_GATEWAY_CMDS:
        try:
            handler = lookup_handler(subcommand)
            result = handler(sub_args, None, console)
            _emit_result(result, json_mode)
            sys.exit(result.exit_code if result else 0)
        except KeyError:
            pass  # fall through to unknown-command handler below

    # I-14: single composition root — BrokerService owns all gateways
    # Phase 4.3: Lazy instrument loading - skip for commands that don't need symbol resolution
    needs_instruments = subcommand in {
        "historical", "history", "search", "instrument",
        "instrument-info", "instruments", "option-chain", "futures",
        "quote", "depth", "stream",  # Market data needs instruments
        "validate", "validate-history", "validate-option-chain",  # Validation needs instruments
    }
    event_bus_service = EventBusService()
    broker_service = BrokerService(
        load_instruments=needs_instruments,
        event_bus=getattr(event_bus_service, "event_bus", None),
    )

    # Set active broker if non-default
    if broker_name != "dhan":
        try:
            broker_service.set_active_broker(broker_name)
        except ValueError as exc:
            if json_mode:
                _print_json({"success": False, "error": str(exc)})
            else:
                console.print(f"[red]{exc}[/red]")
            broker_service.close()
            sys.exit(1)

    try:
        handler = lookup_handler(subcommand)
        result = handler(sub_args, broker_service, console)
        _emit_result(result, json_mode)
        sys.exit(result.exit_code if result else 0)
    except KeyError:
        if json_mode:
            _print_json({"success": False, "error": f"Unknown command: {subcommand}"})
        else:
            console.print(f"[red]Error: Unknown command '{subcommand}'[/red]")
            console.print("[yellow]Run 'tradex --help' for available commands.[/yellow]")
        sys.exit(1)
    except Exception as exc:
        logger.exception("Unhandled exception in command '%s'", subcommand)
        if json_mode:
            _print_json({"success": False, "error": str(exc)})
        else:
            console.print(f"[red]Error: {exc}[/red]")
        sys.exit(1)
    finally:
        broker_service.close()
        
        # Phase 5.3: Display execution time if --timing flag is set
        if show_timing:
            elapsed = time.time() - start_time
            if elapsed > 0.1:  # Only show if >100ms to avoid noise
                console.print(f"[dim]⏱️  Completed in {elapsed:.2f}s[/dim]")
            logger.debug(
                "command_timing",
                extra={
                    "command": subcommand if 'subcommand' in locals() else "unknown",
                    "elapsed_seconds": round(elapsed, 3),
                },
            )


def _emit_result(result: CommandResult | None, json_mode: bool) -> None:
    """Print the command result, respecting json_mode."""
    if not json_mode:
        return
    if result is None:
        _print_json({"success": True})
    elif result.error:
        _print_json({"success": False, "error": result.error, "data": result.data})
    else:
        _print_json({"success": True, "data": result.data})


def _print_json(obj: object) -> None:
    """Print obj as JSON to stdout.  Falls back to repr on serialization errors."""
    try:
        print(_json.dumps(obj, default=str))
    except Exception:
        print(_json.dumps({"success": False, "error": "JSON serialization failed"}))


if __name__ == "__main__":
    main()
