"""CLI command for broker validation dashboard."""

from __future__ import annotations

import logging
import time
from datetime import datetime

from rich.console import Console
from rich.table import Table

logger = logging.getLogger(__name__)


def run(args: list[str], broker_service, console: Console) -> None:
    """Display broker validation dashboard."""
    console.print("\n[bold]TradeXV2 Broker Validation Dashboard[/bold]\n")

    # Get gateways
    try:
        from pathlib import Path

        from brokers.common.intelligent_gateway import IntelligentGateway
        from cli.services.broker_registry import create_gateway

        dhan = create_gateway("dhan", env_path=Path(".env.local"), load_instruments=True)
        upstox = create_gateway("upstox", env_path=Path(".env.upstox"), load_instruments=True)
        if dhan and upstox:
            gw = IntelligentGateway(dhan_gateway=dhan, upstox_gateway=upstox)
        elif dhan:
            gw = dhan
        elif upstox:
            gw = upstox
        else:
            console.print("[red]No broker gateways available[/red]")
            return
    except Exception as e:
        console.print(f"[red]Error creating gateway: {e}[/red]")
        return

    # Check各项状态
    checks = {}

    # Login Status
    try:
        gw.ltp("TCS")
        checks["Login Status"] = ("Connected", "green")
    except Exception as exc:
        logger.debug("dashboard_check_failed", extra={"check": "Login Status", "error": str(exc)})
        checks["Login Status"] = ("Disconnected", "red")

    # Historical Status
    try:
        t0 = time.time()
        gw.history("TCS", timeframe="1D", lookback_days=5)
        latency = (time.time() - t0) * 1000
        checks["Historical Status"] = (f"Healthy ({latency:.0f}ms)", "green")
    except Exception as exc:
        logger.debug(
            "dashboard_check_failed", extra={"check": "Historical Status", "error": str(exc)}
        )
        checks["Historical Status"] = ("Error", "red")

    # Quote Status
    try:
        t0 = time.time()
        gw.quote("TCS")
        latency = (time.time() - t0) * 1000
        checks["Quote Status"] = (f"Healthy ({latency:.0f}ms)", "green")
    except Exception as exc:
        logger.debug("dashboard_check_failed", extra={"check": "Quote Status", "error": str(exc)})
        checks["Quote Status"] = ("Error", "red")

    # Option Chain Status
    try:
        t0 = time.time()
        chain = gw.option_chain("NIFTY")
        latency = (time.time() - t0) * 1000
        strikes = len(chain.get("strikes", []))
        checks["Option Chain"] = (f"Healthy ({strikes} strikes, {latency:.0f}ms)", "green")
    except Exception as exc:
        logger.debug("dashboard_check_failed", extra={"check": "Option Chain", "error": str(exc)})
        checks["Option Chain"] = ("Error", "red")

    # Future Chain Status
    try:
        t0 = time.time()
        futures = gw.future_chain("NIFTY")
        latency = (time.time() - t0) * 1000
        contracts = len(futures.get("contracts", []))
        checks["Future Chain"] = (f"Healthy ({contracts} contracts, {latency:.0f}ms)", "green")
    except Exception as exc:
        logger.debug("dashboard_check_failed", extra={"check": "Future Chain", "error": str(exc)})
        checks["Future Chain"] = ("Error", "red")

    # Last Validation
    checks["Last Validation"] = (datetime.now().strftime("%H:%M:%S"), "cyan")

    # System Health
    all_healthy = all(v[1] == "green" for v in checks.values() if v[1] in ("green", "red"))
    checks["System Health"] = ("PASS" if all_healthy else "FAIL", "green" if all_healthy else "red")

    # Display dashboard
    table = Table(
        show_header=True, header_style="bold", title="TradeXV2 Broker Validation Dashboard"
    )
    table.add_column("Metric", style="cyan", width=20)
    table.add_column("Status", width=40)

    for metric, (status, color) in checks.items():
        table.add_row(metric, f"[{color}]{status}[/{color}]")

    console.print(table)
