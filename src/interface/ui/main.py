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

from interface.ui.commands import (
    asset as cmd_asset,
)
from interface.ui.commands import (
    auth as cmd_auth,
)
from interface.ui.commands import (
    benchmark as cmd_benchmark,
)
from interface.ui.commands import (
    broker as cmd_broker,
)
from interface.ui.commands import (
    cache_management as cmd_cache_management,
)
from interface.ui.commands import (
    compare as cmd_compare,
)
from interface.ui.commands import (
    dashboard as cmd_dashboard,
)
from interface.ui.commands import (
    doctor as cmd_doctor,
)
from interface.ui.commands import (
    events as cmd_events,
)
from interface.ui.commands import (
    instrument as cmd_instrument,
)
from interface.ui.commands import (
    instruments as cmd_instruments,
)
from interface.ui.commands import (
    journal as cmd_journal,
)
from interface.ui.commands import (
    livefeed as cmd_livefeed,
)
from interface.ui.commands import (
    load_test as cmd_load_test,
)
from interface.ui.commands import (
    market as cmd_market,
)
from interface.ui.commands import (
    news as cmd_news,
)
from interface.ui.commands import (
    options_sync as cmd_options_sync,
)
from interface.ui.commands import (
    quality_report as cmd_quality_report,
)
from interface.ui.commands import (
    search as cmd_search,
)
from interface.ui.commands import (
    validate as cmd_validate,
)
from interface.ui.commands import (
    validate_history as cmd_validate_history,
)
from interface.ui.commands import (
    validate_option_chain as cmd_validate_option_chain,
)
from interface.ui.commands import (
    views as cmd_views,
)
from interface.ui.commands import (
    websocket as cmd_websocket,
)
from interface.ui.commands.events import EventBusService
from interface.ui.commands.registry import lookup_handler, register_handler
from interface.ui.services import (
    compose as _compose,  # noqa: F401  (wires session opener on import)
)
from interface.ui.services.broker_registry import bootstrap_gateway
from interface.ui.services.broker_service import BrokerService


def _run_analytics_lazy(*args, **kwargs):
    from interface.ui.commands import analytics as cmd_analytics

    return cmd_analytics.run(*args, **kwargs)


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
    "instrument-info": cmd_instrument.run,
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
    "asset": cmd_asset.run,
    "feed": cmd_livefeed.run,
    "auth": cmd_auth.run,
    "doctor": cmd_doctor.run,
    "load-test": cmd_load_test.run,
    "news": cmd_news.run,
    "analytics": _run_analytics_lazy,
    "views": cmd_views.run_views,
    "cache": cmd_cache_management.run,
}
for _name, _fn in COMMAND_HANDLERS.items():
    register_handler(_name, _fn)


# Read-only market-data commands: must NOT touch trading_context (OMS replay).
MARKET_ONLY_CMDS = frozenset(
    {
        "feed",
        "quote",
        "depth",
        "option-chain",
        "futures",
        "historical",
        "history",
        "stream",
        "websocket",
        "search",
        "instrument",
        "instruments",
        "asset",
        "news",
    }
)


def _try_create_gateway(
    broker: str = "dhan",
    load_instruments: bool = True,
    event_bus: Any | None = None,
    lifecycle: Any | None = None,
) -> Any:
    """Bootstrap a broker gateway with automatic auth probe; None on failure.

    Production path: create → structural readiness → network probe → at most
    one token remint. Delegates to :func:`bootstrap_gateway`.
    """
    try:
        result = bootstrap_gateway(
            broker=broker,
            load_instruments=load_instruments,
            event_bus=event_bus,
            lifecycle=lifecycle,
            require_authenticated=True,
        )
        if result.live_ready:
            return result.gateway
        return None
    except Exception:
        return None


def main() -> None:
    """Parse CLI arguments and route to commands or TUI."""
    from infrastructure.correlation import with_correlation

    with with_correlation():
        _run_cli()


def _run_cli() -> None:
    """CLI body (runs inside a correlation context)."""
    exit_code = 0
    args = sys.argv[1:]

    broker_name = "dhan"
    if "--broker" in args:
        idx = args.index("--broker")
        if idx + 1 < len(args):
            broker_name = args[idx + 1].lower()
            args = args[:idx] + args[idx + 2 :]

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
        console.print(
            "[yellow]Usage: tradex <command> [args] [--broker dhan|upstox] [--risk-fail-open][/yellow]\n"
        )
        console.print("[bold]Commands:[/bold]")
        cmds = [
            ("broker", "Show broker connection info"),
            ("analytics", "Run analytics (scan, rank, backtest, paper, sectors)"),
            ("validate", "Validate data (broker health or CSV file)"),
            ("benchmark", "Benchmark broker latency"),
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
            ("asset", "OOP-by-segment data (equity/spot/index/options/futures)"),
            ("feed", "Live feed smoke test (feed test <segment> <symbol>)"),
            ("auth", "Auth status / token refresh"),
            ("doctor", "System diagnostics"),
            ("load-test", "Load test broker"),
            ("news", "Market news"),
            ("journal", "Trade journal (record, close, list, summary)"),
            ("views", "DuckDB analytics view management"),
            ("options-sync", "Sync option data from broker federation (daily cron)"),
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

    # Fail early for unknown commands to prevent hanging on gateway startup
    if subcommand not in COMMAND_HANDLERS:
        console.print(f"[red]Error: Unknown command '{subcommand}'[/red]")
        console.print(
            "[yellow]Available commands: broker, analytics, quote, depth, option-chain, futures, historical/history, stream, websocket, events, search, instrument, instruments, doctor, load-test, news[/yellow]"
        )
        sys.exit(1)

    # Commands that don't need a broker gateway
    _NO_GATEWAY_CMDS = {"help", "journal", "views", "validate", "options-sync"}

    # Read-only market-data: skip trading_context (OMS event-log replay).
    # Handlers use market_gateway / platform_bridge instead.
    _MARKET_ONLY_CMDS = MARKET_ONLY_CMDS

    # Commands that need instruments (historical, search, instruments)
    _NEEDS_INSTRUMENTS = {
        "historical",
        "history",
        "search",
        "instrument",
        "instruments",
        "option-chain",
        "futures",
    }

    runtime = None
    gateway = None
    broker_service: BrokerService | Any
    event_bus_service = EventBusService()
    tc = None
    _gw: Any = None

    broker_service = BrokerService(authorize_risk_fail_open=authorize_risk_fail_open)

    def _get_gateway() -> Any:
        nonlocal _gw
        if _gw is None:
            load_inst = subcommand in _NEEDS_INSTRUMENTS
            _gw = _try_create_gateway(broker_name, load_instruments=load_inst)
        return _gw

    if subcommand not in _NO_GATEWAY_CMDS and subcommand not in _MARKET_ONLY_CMDS:
        load_inst = subcommand in _NEEDS_INSTRUMENTS
        gateway = _try_create_gateway(
            broker_name,
            load_instruments=load_inst,
            event_bus=event_bus_service.event_bus,
            lifecycle=broker_service.lifecycle,
        )
        _gw = gateway
        tc = broker_service.trading_context
        if tc is not None:
            event_bus_service = EventBusService(event_bus=tc.event_bus)

    # 3. Registry-only subcommand routing
    try:
        if subcommand == "validate" and cmd_args and cmd_args[0] in ("history", "option-chain"):
            nested = cmd_args[0]
            rest = cmd_args[1:]
            if nested == "history":
                cmd_validate_history.run(rest, broker_service, console)
            else:
                cmd_validate_option_chain.run(rest, broker_service, console)
        else:
            try:
                handler = lookup_handler(subcommand)
            except KeyError:
                handler = None
            if handler is None:
                console.print(f"[red]Error: Unknown command '{subcommand}'[/red]")
                exit_code = 1
            elif subcommand == "events":
                handler(cmd_args, event_bus_service, console)
            elif subcommand == "journal" or subcommand in ("views", "options-sync"):
                handler(cmd_args, console)
            elif subcommand == "analytics":
                result = handler(cmd_args, broker_service, console)
                if result is not None and not getattr(result, "success", True):
                    exit_code = 1
            elif handler is cmd_market.run:
                handler([subcommand, *cmd_args], broker_service, console)
            else:
                handler(cmd_args, broker_service, console)
    finally:
        if runtime is not None:
            try:
                runtime.lifecycle.stop_all()
            except Exception as exc:
                logger.debug("runtime_stop_failed: %s", exc)
        if broker_service is not None:
            broker_service.close()
        if gateway is not None:
            try:
                gateway.close()
            except Exception as exc:
                logger.debug("gateway_close_failed: %s", exc)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
