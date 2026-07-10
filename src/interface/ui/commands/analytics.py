"""CLI command handler for analytics — thin router."""

from __future__ import annotations

import logging

from rich.console import Console

from interface.ui.commands.registry import CommandResult

from .analytics_backtest import run_backtest, run_paper
from .analytics_compare import run_compare
from .analytics_datalake import run_datalake_backtest
from .analytics_halftrend import run_halftrend, run_halftrend_scan
from .analytics_optimize import run_optimize
from .analytics_replay import run_replay
from .analytics_research import run_orderflow, run_probability
from .analytics_scanner import run_rank, run_scan, run_scanner_command
from .analytics_sector import (
    run_breadth,
    run_sector,
    run_sector_full,
    run_sector_rotation,
    run_sector_strength,
    run_sector_volume,
)
from .analytics_stock import run_symbol_command
from .analytics_strategies import run_strategies
from .analytics_walkforward import run_walkforward

logger = logging.getLogger(__name__)


def run(args: list[str], broker_service, console: Console) -> CommandResult:
    """Route analytics subcommands and return CommandResult for --json mode.

    Phase 5.2: Standardized to return CommandResult instead of None.
    """
    if not args:
        console.print("[yellow]Usage: tradex analytics <command> [args][/yellow]")
        console.print(
            "[dim]Commands: stock, future, option, volatility, volume-profile, breadth, sector, sector-rotation, sector-volume, sector-strength, sector-full, backtest, paper, replay, walkforward, strategies, scan, rank, scan-momentum, scan-volume, scan-rs, scan-breakout, halftrend, halftrend-scan, datalake-backtest, orderflow, probability, optimize, compare[/dim]"
        )
        return CommandResult(success=False, error="Missing analytics subcommand")

    command = args[0].lower()
    try:
        if command in {"stock", "future", "option", "options", "volatility", "volume-profile"}:
            run_symbol_command(command, args[1:], broker_service, console)
            return CommandResult(success=True, data={"command": command})
        elif command == "breadth":
            run_breadth(args[1:], console)
            return CommandResult(success=True, data={"command": "breadth"})
        elif command == "sector":
            run_sector(args[1:], console)
            return CommandResult(success=True, data={"command": "sector"})
        elif command == "sector-rotation":
            run_sector_rotation(args[1:], console)
            return CommandResult(success=True, data={"command": "sector-rotation"})
        elif command == "sector-volume":
            run_sector_volume(args[1:], console)
            return CommandResult(success=True, data={"command": "sector-volume"})
        elif command == "sector-strength":
            run_sector_strength(args[1:], console)
            return CommandResult(success=True, data={"command": "sector-strength"})
        elif command == "sector-full":
            run_sector_full(args[1:], console)
            return CommandResult(success=True, data={"command": "sector-full"})
        elif command == "backtest":
            run_backtest(args[1:], console)
            return CommandResult(success=True, data={"command": "backtest"})
        elif command == "paper":
            run_paper(args[1:], console)
            return CommandResult(success=True, data={"command": "paper"})
        elif command == "scan":
            run_scan(args[1:], console)
            return CommandResult(success=True, data={"command": "scan"})
        elif command == "rank":
            run_rank(args[1:], console)
            return CommandResult(success=True, data={"command": "rank"})
        elif command == "scan-momentum":
            run_scanner_command("momentum", args[1:], broker_service, console)
            return CommandResult(success=True, data={"command": "scan-momentum"})
        elif command == "scan-volume":
            run_scanner_command("volume", args[1:], broker_service, console)
            return CommandResult(success=True, data={"command": "scan-volume"})
        elif command == "scan-rs":
            run_scanner_command("rs", args[1:], broker_service, console)
            return CommandResult(success=True, data={"command": "scan-rs"})
        elif command == "scan-breakout":
            run_scanner_command("breakout", args[1:], broker_service, console)
            return CommandResult(success=True, data={"command": "scan-breakout"})
        elif command == "halftrend":
            run_halftrend(args[1:], broker_service, console)
            return CommandResult(success=True, data={"command": "halftrend"})
        elif command == "halftrend-scan":
            run_halftrend_scan(args[1:], console)
            return CommandResult(success=True, data={"command": "halftrend-scan"})
        elif command == "datalake-backtest":
            run_datalake_backtest(args[1:], console)
            return CommandResult(success=True, data={"command": "datalake-backtest"})
        elif command == "orderflow":
            run_orderflow(args[1:], console)
            return CommandResult(success=True, data={"command": "orderflow"})
        elif command == "probability":
            run_probability(args[1:], console)
            return CommandResult(success=True, data={"command": "probability"})
        elif command == "replay":
            run_replay(args[1:], console)
            return CommandResult(success=True, data={"command": "replay"})
        elif command == "optimize":
            run_optimize(args[1:], console)
            return CommandResult(success=True, data={"command": "optimize"})
        elif command == "compare":
            run_compare(args[1:], console)
            return CommandResult(success=True, data={"command": "compare"})
        elif command == "walkforward":
            run_walkforward(args[1:], console)
            return CommandResult(success=True, data={"command": "walkforward"})
        elif command == "strategies":
            run_strategies(args[1:], console)
            return CommandResult(success=True, data={"command": "strategies"})
        else:
            console.print(f"[red]Unknown analytics command '{command}'.[/red]")
            return CommandResult(success=False, error=f"Unknown analytics command: {command}")
    except Exception as exc:
        logger.exception("analytics_command_failed", extra={"command": command})
        console.print(f"[red]Analytics error: {exc}[/red]")
        return CommandResult(success=False, error=str(exc))
