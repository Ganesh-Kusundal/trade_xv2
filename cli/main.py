"""Main CLI/TUI entrypoint for TradeXV2 diagnostic terminal.

I-10 / I-14 / P0-10 (2026-06-17): dict-based dispatch, single
composition root via BrokerService, proper exit codes, and --json
output mode.
"""

from __future__ import annotations

import json as _json
import logging
import sys
from pathlib import Path
from typing import Any

from rich.console import Console

from brokers.common.auth.environment_bootstrap import bootstrap_environment

# Initialize centralized logging BEFORE any other imports that log
from infrastructure.logging_config import configure_logging

configure_logging(service="cli")

# Load canonical broker env files once at startup.
bootstrap_environment(Path(__file__).resolve().parent.parent)

# isort: off
from cli.commands import (  # noqa: E402
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
from cli.commands.market_handlers import (  # noqa: E402
    handle_depth,
    handle_futures,
    handle_history,
    handle_option_chain,
    handle_orders,
    handle_quote,
    handle_stream,
    handle_validate,
)
from cli.commands.registry import (  # noqa: E402
    DISPATCH_TABLE,
    CommandResult,
    lookup_handler,
    register_handler,
    register as _register_cmd,
)
from cli.services.broker_service import BrokerService  # noqa: E402
from cli.services.event_bus_service import EventBusService  # noqa: E402
# isort: on

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
_register_cmd("certify", "cli.commands.certify")


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
    ("super-order", lambda a, bs, c: cmd_extended_orders.super_order(a, bs, c)),
    ("forever-order", lambda a, bs, c: cmd_extended_orders.forever_order(a, bs, c)),
    ("trigger", lambda a, bs, c: cmd_extended_orders.trigger(a, bs, c)),
    ("margin", lambda a, bs, c: cmd_extended_orders.margin(a, bs, c)),
    ("exit-all", lambda a, bs, c: cmd_extended_orders.exit_all(a, bs, c)),
    ("ledger", lambda a, bs, c: cmd_extended_orders.ledger(a, bs, c)),
    ("edis", lambda a, bs, c: cmd_extended_orders.edis(a, bs, c)),
    ("ip", lambda a, bs, c: cmd_extended_orders.ip(a, bs, c)),
    ("profile", lambda a, bs, c: cmd_extended_orders.profile(a, bs, c)),
    ("gtt-order", lambda a, bs, c: cmd_extended_orders.gtt_order(a, bs, c)),
    ("cover-order", lambda a, bs, c: cmd_extended_orders.cover_order(a, bs, c)),
    ("slice-order", lambda a, bs, c: cmd_extended_orders.slice_order(a, bs, c)),
    ("broker-kill-switch", lambda a, bs, c: cmd_extended_orders.broker_kill_switch(a, bs, c)),
    ("ipo", lambda a, bs, c: cmd_extended_orders.ipo(a, bs, c)),
    ("mf", lambda a, bs, c: cmd_extended_orders.mf(a, bs, c)),
    ("payout", lambda a, bs, c: cmd_extended_orders.payout(a, bs, c)),
    ("fundamentals", lambda a, bs, c: cmd_extended_orders.fundamentals(a, bs, c)),
    # Risk management commands (Agent 2)
    ("risk", lambda a, bs, c: cmd_risk_controls.run(a, bs, c)),
    # Cache management (Agent 4)
    ("cache", lambda a, bs, c: cmd_cache_management.run(a, bs, c)),
    # Signature-adapted wrappers (routed through _wrap helper)
    ("holdings", lambda a, bs, c: _wrap(cmd_portfolio.show_holdings, bs, c)),
    ("positions", lambda a, bs, c: _wrap(cmd_portfolio.show_positions, bs, c)),
    ("trades", lambda a, bs, c: _wrap(cmd_oms.show_trades, bs, c)),
    ("oms", lambda a, bs, c: _wrap(cmd_oms.show_oms_summary, bs, c)),
    ("journal", lambda a, bs, c: _wrap(cmd_journal.run_journal, a, c)),
    ("views", lambda a, bs, c: _wrap(cmd_views.run_views, a, c)),
    ("options-sync", lambda a, bs, c: _wrap(cmd_options_sync.run_options_sync, a, c)),
    ("events", lambda a, bs, c: _wrap(cmd_events.run, a, EventBusService(), c)),
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

# Populate the registry dispatch table
for _name, _fn in _DISPATCH:
    register_handler(_name, _fn)


# ── Main entry point ───────────────────────────────────────────────────────

# Commands that do NOT need a broker gateway at all (no BrokerService init).
_NO_GATEWAY_CMDS = frozenset({"help", "journal", "views", "options-sync"})

# P-1.3: Read-only commands that don't need TradingContext/OMS lock
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
    console = Console(quiet=True, highlight=False) if json_mode else Console()

    if verbose:
        logger.debug("verbose_mode_enabled", extra={"broker": broker_name, "cli_args": cmd_args})

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
        "historical",
        "history",
        "search",
        "instrument",
        "instrument-info",
        "instruments",
        "option-chain",
        "futures",
        "quote",
        "depth",
        "stream",  # Market data needs instruments
        "validate",
        "validate-history",
        "validate-option-chain",  # Validation needs instruments
    }

    # P-1.3: Readonly mode - skip TradingContext/OMS for market data commands
    readonly = subcommand in _READONLY_COMMANDS

    event_bus_service = EventBusService()
    broker_service = BrokerService(
        load_instruments=needs_instruments,
        event_bus=getattr(event_bus_service, "event_bus", None),
        readonly=readonly,  # P-1.3: readonly mode flag
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
                    "command": subcommand if "subcommand" in locals() else "unknown",
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
