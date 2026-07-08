"""Main CLI/TUI entrypoint for TradeXV2 diagnostic terminal.

I-10 / I-14 / P0-10 (2026-06-17): dict-based dispatch, single
composition root via BrokerService, proper exit codes, and --json
output mode.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from rich.console import Console

from infrastructure.io.environment_bootstrap import bootstrap_environment
from infrastructure.logging_config import configure_logging

# isort: off
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
    extended_orders as cmd_extended_orders,
    instrument_info as cmd_instrument_info,
    instruments as cmd_instruments,
    journal as cmd_journal,
    load_test as cmd_load_test,
    news as cmd_news,
    oms as cmd_oms,
    options_sync as cmd_options_sync,
    order_composition as cmd_order_composition,
    order_placement as cmd_order_placement,
    portfolio as cmd_portfolio,
    quality_report as cmd_quality_report,
    risk_controls as cmd_risk_controls,
    search as cmd_search,
    validate_history as cmd_validate_history,
    validate_option_chain as cmd_validate_option_chain,
    views as cmd_views,
    websocket as cmd_websocket,
)
from cli.commands.market_handlers import (
    handle_depth,
    handle_futures,
    handle_history,
    handle_option_chain,
    handle_orders,
    handle_quote,
    handle_stream,
    handle_validate,
)
from cli.commands.registry import (
    DISPATCH_TABLE,
    CommandResult,
    lookup_handler,
    register_handler,
)
from cli.services.broker_service import BrokerService
from cli.services.event_bus_service import EventBusService
# isort: on


# ── Helpers ─────────────────────────────────────────────────────────────────


def _print_help(console: Console) -> None:
    console.print("[bold]TradeXV2 CLI[/bold]\n")
    console.print(
        "[yellow]Usage: tradex <command> [args] [--broker dhan|upstox] [--json] [--verbose] [--timing][/yellow]\n"
    )
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
        ("certify", "Run broker certification suite"),
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


def _adapt_to_command_result(_fn: Any, *args: Any, **kwargs: Any) -> CommandResult:
    """Invoke *fn* and return a successful CommandResult."""
    _fn(*args, **kwargs)
    return CommandResult(success=True)


_EXTENDED_ORDER_FUNCS = [
    "super_order", "forever_order", "trigger", "margin", "exit_all",
    "ledger", "edis", "ip", "profile", "gtt_order", "cover_order",
    "slice_order", "broker_kill_switch", "ipo", "mf", "payout", "fundamentals",
]


def _extended_dispatch() -> list[tuple[str, Any]]:
    """Build dispatch entries for all extended broker feature commands."""
    return [
        (name.replace("_", "-"), lambda a, bs, c, fn=getattr(cmd_extended_orders, name): fn(a, bs, c))
        for name in _EXTENDED_ORDER_FUNCS
    ]


_HANDLERS: list[tuple[str, Any]] = [
    # Standard routing — module-level run() functions
    ("broker", cmd_broker.run),
    ("dashboard", cmd_dashboard.run),
    ("benchmark", cmd_benchmark.run),
    ("analytics", cmd_analytics.run),
    ("compare", cmd_compare.run),
    ("quality-report", cmd_quality_report.run),
    ("instrument", cmd_instrument_info.run),
    ("instrument-info", cmd_instrument_info.run),
    ("account", cmd_account.run),
    ("funds", cmd_account.run),
    ("search", cmd_search.run),
    ("instruments", cmd_instruments.run),
    ("doctor", cmd_doctor.run),
    ("load-test", cmd_load_test.run),
    ("news", cmd_news.run),
    ("websocket", cmd_websocket.run),
    ("validate-history", cmd_validate_history.run),
    ("validate-option-chain", cmd_validate_option_chain.run),
    # Order lifecycle commands (Agent 1)
    ("place-order", lambda a, bs, c: cmd_order_placement.place_order(a, bs, c)),
    ("cancel-order", lambda a, bs, c: cmd_order_placement.cancel_order(a, bs, c)),
    ("modify-order", lambda a, bs, c: cmd_order_placement.modify_order(a, bs, c)),
    ("place-orders", lambda a, bs, c: cmd_order_placement.place_orders_batch(a, bs, c)),
    # Order composition patterns (Agent 3)
    ("bracket-order", lambda a, bs, c: cmd_order_composition.place_bracket_order(a, bs, c)),
    ("oco-order", lambda a, bs, c: cmd_order_composition.place_oco_order(a, bs, c)),
    ("basket-order", lambda a, bs, c: cmd_order_composition.place_basket_order(a, bs, c)),
    # Extended broker features
    *_extended_dispatch(),
    # Risk management commands (Agent 2)
    ("risk", lambda a, bs, c: cmd_risk_controls.run(a, bs, c)),
    # Cache management (Agent 4)
    ("cache", lambda a, bs, c: cmd_cache_management.run(a, bs, c)),
    # Signature-adapted wrappers
    ("holdings", lambda a, bs, c: _adapt_to_command_result(cmd_portfolio.show_holdings, bs, c)),
    ("positions", lambda a, bs, c: _adapt_to_command_result(cmd_portfolio.show_positions, bs, c)),
    ("trades", lambda a, bs, c: _adapt_to_command_result(cmd_oms.show_trades, bs, c)),
    ("oms", lambda a, bs, c: _adapt_to_command_result(cmd_oms.show_oms_summary, bs, c)),
    ("journal", lambda a, bs, c: _adapt_to_command_result(cmd_journal.run_journal, a, c)),
    ("views", lambda a, bs, c: _adapt_to_command_result(cmd_views.run_views, a, c)),
    ("options-sync", lambda a, bs, c: _adapt_to_command_result(cmd_options_sync.run_options_sync, a, c)),
    ("events", lambda a, bs, c: _adapt_to_command_result(cmd_events.run, a, EventBusService(), c)),
    # Market data handlers — extracted from inline to cli/commands/market_handlers.py (REF-013)
    ("quote", handle_quote),
    ("depth", handle_depth),
    ("historical", handle_history),
    ("history", handle_history),
    ("option-chain", handle_option_chain),
    ("futures", handle_futures),
    ("stream", handle_stream),
    ("orders", handle_orders),
    ("validate", handle_validate),
]

for _name, _fn in _HANDLERS:
    register_handler(_name, _fn)


_NO_GATEWAY_CMDS = frozenset({"help", "journal", "views", "options-sync"})

_READONLY_COMMANDS = frozenset({
    "quote", "depth", "option-chain", "futures",
    "historical", "history", "stream",
    "search", "instrument", "instrument-info", "instruments",
    "news",
})


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


logger = logging.getLogger(__name__)


def _build_broker_context(
    subcommand: str,
    broker_name: str,
    console: Console,
    json_mode: bool,
) -> BrokerService:
    """Create and configure a BrokerService for the given subcommand."""
    needs_instruments = subcommand in {
        "historical", "history", "search",
        "instrument", "instrument-info", "instruments",
        "option-chain", "futures", "quote", "depth", "stream",
        "validate", "validate-history", "validate-option-chain",
    }
    readonly = subcommand in _READONLY_COMMANDS

    event_bus_service = EventBusService()
    broker_service = BrokerService(
        load_instruments=needs_instruments,
        event_bus=getattr(event_bus_service, "event_bus", None),
        readonly=readonly,
    )

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

    return broker_service


def _dispatch_command(
    subcommand: str,
    sub_args: list[str],
    broker_service: BrokerService,
    console: Console,
    json_mode: bool,
) -> None:
    """Look up and execute the handler for *subcommand*, then sys.exit."""
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


def _display_timing(
    start_time: float,
    subcommand: str,
    console: Console,
) -> None:
    """Print elapsed time if it exceeds 100ms."""
    import time

    elapsed = time.time() - start_time
    if elapsed > 0.1:
        console.print(f"[dim]\u23f1\ufe0f  Completed in {elapsed:.2f}s[/dim]")
    logger.debug(
        "command_timing",
        extra={
            "command": subcommand,
            "elapsed_seconds": round(elapsed, 3),
        },
    )


def main() -> None:
    """Parse CLI arguments and route to commands or TUI."""
    import time

    configure_logging(service="cli")
    bootstrap_environment(Path(__file__).resolve().parent.parent)

    start_time = time.time()

    broker_name, cmd_args, json_mode, verbose, show_timing = _parse_flags(sys.argv[1:])

    console: Console = Console(quiet=True, highlight=False) if json_mode else Console()

    if verbose:
        logger.debug("verbose_mode_enabled", extra={"broker": broker_name, "cli_args": cmd_args})

    if not cmd_args or cmd_args[0] in ("--help", "-h", "help"):
        _print_help(console)
        if json_mode:
            _print_json({"help": True, "commands": list(DISPATCH_TABLE)})
        sys.exit(0)

    subcommand = cmd_args[0].lower()
    sub_args = cmd_args[1:]

    if subcommand in _NO_GATEWAY_CMDS:
        try:
            handler = lookup_handler(subcommand)
            result = handler(sub_args, None, console)
            _emit_result(result, json_mode)
            sys.exit(result.exit_code if result else 0)
        except KeyError:
            pass

    broker_service = _build_broker_context(subcommand, broker_name, console, json_mode)
    try:
        _dispatch_command(subcommand, sub_args, broker_service, console, json_mode)
    finally:
        broker_service.close()
        if show_timing:
            _display_timing(start_time, subcommand, console)


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
        print(json.dumps(obj, default=str))
    except Exception:
        print(json.dumps({"success": False, "error": "JSON serialization failed"}))


if __name__ == "__main__":
    main()
