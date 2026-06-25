"""CLI command for option chain validation."""

from __future__ import annotations

import time

from rich.console import Console
from rich.table import Table


def run(args: list[str], broker_service, console: Console) -> None:
    """Validate option chain data quality."""
    if not args:
        console.print("[yellow]Usage: tradex validate option-chain <symbol>[/yellow]")
        return

    symbol = args[0].upper()

    console.print(f"\n[bold]Option Chain Validation: {symbol}[/bold]\n")

    # Get gateway
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

    # Validate Dhan option chain
    console.print("[cyan]--- Dhan ---[/cyan]")
    try:
        t0 = time.time()
        chain = gw.dhan.option_chain(symbol)
        latency = (time.time() - t0) * 1000

        spot = chain.get("spot", 0)
        strikes = chain.get("strikes", [])
        expiry = chain.get("expiry", "N/A")

        # Find ATM
        atm_strike = (
            min(strikes, key=lambda s: abs(float(s["strike"]) - float(spot)))
            if strikes and spot
            else None
        )

        # Calculate PCR
        total_call_oi = sum(s.get("call", {}).get("oi", 0) or 0 for s in strikes)
        total_put_oi = sum(s.get("put", {}).get("oi", 0) or 0 for s in strikes)
        pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0

        # Find highest OI
        max_call_oi = (
            max(strikes, key=lambda s: s.get("call", {}).get("oi", 0) or 0) if strikes else None
        )
        max_put_oi = (
            max(strikes, key=lambda s: s.get("put", {}).get("oi", 0) or 0) if strikes else None
        )

        # Validation checks
        issues = []
        if not strikes:
            issues.append("no strikes")
        if atm_strike is None:
            issues.append("ATM not found")
        if pcr == 0:
            issues.append("PCR is zero")

        status = "PASS" if not issues else "WARN: " + ", ".join(issues)

        table = Table(show_header=False, show_edge=False)
        table.add_column("Metric", style="cyan", width=20)
        table.add_column("Value", width=40)
        table.add_row("Spot", f"₹{spot:,.2f}")
        table.add_row("Expiry", str(expiry))
        table.add_row("Strikes", str(len(strikes)))
        table.add_row("ATM Strike", f"₹{atm_strike['strike']:,.2f}" if atm_strike else "N/A")
        table.add_row("PCR", f"{pcr:.2f}")
        table.add_row(
            "Highest Call OI",
            f"₹{max_call_oi['strike']:,.0f} (OI={max_call_oi.get('call', {}).get('oi', 0):,})"
            if max_call_oi
            else "N/A",
        )
        table.add_row(
            "Highest Put OI",
            f"₹{max_put_oi['strike']:,.0f} (OI={max_put_oi.get('put', {}).get('oi', 0):,})"
            if max_put_oi
            else "N/A",
        )
        table.add_row("Latency", f"{latency:.0f}ms")
        table.add_row("Status", status)
        console.print(table)

    except Exception as e:
        console.print(f"  ERROR: {e}")

    # Upstox (deprecated)
    console.print("\n[cyan]--- Upstox ---[/cyan]")
    console.print("  Option chain endpoint: DEPRECATED")
    console.print("  Status: N/A")
