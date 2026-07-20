"""CLI command for broker validation dashboard."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from domain.enums import BrokerId
from interface.ui.commands._broker import broker_id_from
from interface.ui.services.broker_ops import get_history, get_option_chain, get_quote

logger = logging.getLogger(__name__)


def run(args: list[str], broker_service, console: Console) -> None:
    """Display broker validation dashboard."""
    console.print("\n[bold]TradeXV2 Broker Validation Dashboard[/bold]\n")

    checks: dict[str, tuple[str, str]] = {}
    env = {"env_path": str(Path(".env.local")), "load_instruments": True}

    try:
        try:
            get_quote(broker_id_from(None, default=BrokerId.DHAN), "TCS", **env)
            checks["Login Status"] = ("Connected", "green")
        except Exception as exc:
            logger.debug(
                "dashboard_check_failed", extra={"check": "Login Status", "error": str(exc)}
            )
            checks["Login Status"] = ("Disconnected", "red")

        try:
            t0 = time.time()
            get_history(broker_id_from(None, default=BrokerId.DHAN), "TCS", days=5, **env)
            latency = (time.time() - t0) * 1000
            checks["Historical Status"] = (f"Healthy ({latency:.0f}ms)", "green")
        except Exception as exc:
            logger.debug(
                "dashboard_check_failed", extra={"check": "Historical Status", "error": str(exc)}
            )
            checks["Historical Status"] = ("Error", "red")

        try:
            t0 = time.time()
            get_quote(broker_id_from(None, default=BrokerId.DHAN), "TCS", **env)
            latency = (time.time() - t0) * 1000
            checks["Quote Status"] = (f"Healthy ({latency:.0f}ms)", "green")
        except Exception as exc:
            logger.debug(
                "dashboard_check_failed", extra={"check": "Quote Status", "error": str(exc)}
            )
            checks["Quote Status"] = ("Error", "red")

        try:
            t0 = time.time()
            chain = get_option_chain(broker_id_from(None, default=BrokerId.DHAN), "NIFTY", **env)
            latency = (time.time() - t0) * 1000
            strikes = len(getattr(chain, "strikes", []) or [])
            checks["Option Chain"] = (f"Healthy ({strikes} strikes, {latency:.0f}ms)", "green")
        except Exception as exc:
            logger.debug(
                "dashboard_check_failed", extra={"check": "Option Chain", "error": str(exc)}
            )
            checks["Option Chain"] = ("Error", "red")

        checks["Future Chain"] = ("Skipped (use tradex futures)", "cyan")
    except Exception as e:
        console.print(f"[red]Error running dashboard checks: {e}[/red]")
        return

    checks["Last Validation"] = (datetime.now().strftime("%H:%M:%S"), "cyan")
    all_healthy = all(v[1] == "green" for v in checks.values() if v[1] in ("green", "red"))
    checks["System Health"] = ("PASS" if all_healthy else "FAIL", "green" if all_healthy else "red")

    table = Table(
        show_header=True, header_style="bold", title="TradeXV2 Broker Validation Dashboard"
    )
    table.add_column("Metric", style="cyan", width=20)
    table.add_column("Status", width=40)

    for metric, (status, color) in checks.items():
        table.add_row(metric, f"[{color}]{status}[/{color}]")

    console.print(table)
