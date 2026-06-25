"""CLI command for historical data quality validation."""

from __future__ import annotations

import time

from rich.console import Console
from rich.table import Table


def run(args: list[str], broker_service, console: Console) -> None:
    """Validate historical data quality."""
    if not args:
        console.print("[yellow]Usage: tradex validate history <symbol>[/yellow]")
        return

    symbol = args[0].upper()

    console.print(f"\n[bold]Historical Data Quality: {symbol}[/bold]\n")

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

    # Validate for each broker
    for name, broker in [("Dhan", gw.dhan), ("Upstox", gw.upstox)]:
        console.print(f"\n[cyan]--- {name} ---[/cyan]")
        try:
            t0 = time.time()
            df = broker.history(symbol, timeframe="1D", lookback_days=30)
            latency = (time.time() - t0) * 1000

            rows = len(df)
            duplicates = df.duplicated(subset=["timestamp"]).sum() if not df.empty else 0
            schema_ok = list(df.columns) == [
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "oi",
                "symbol",
                "exchange",
                "timeframe",
            ]

            # Check for out-of-order candles
            if not df.empty and "timestamp" in df.columns:
                out_of_order = (df["timestamp"].diff().dt.total_seconds() < 0).sum()
            else:
                out_of_order = 0

            # Check for missing candles (weekdays)
            if not df.empty and "timestamp" in df.columns:
                date_range = (df["timestamp"].max() - df["timestamp"].min()).days
                expected_candles = date_range * 5 / 7  # ~5 trading days per week
                completeness = (rows / expected_candles * 100) if expected_candles > 0 else 100
            else:
                completeness = 0

            # Check volume anomalies (zero volume)
            if not df.empty and "volume" in df.columns:
                zero_volume = (df["volume"] == 0).sum()
            else:
                zero_volume = 0

            # Determine status
            issues = []
            if duplicates > 0:
                issues.append(f"{duplicates} duplicates")
            if out_of_order > 0:
                issues.append(f"{out_of_order} out-of-order")
            if zero_volume > 0:
                issues.append(f"{zero_volume} zero-volume")
            if not schema_ok:
                issues.append("schema mismatch")

            status = "PASS" if not issues else "WARN: " + ", ".join(issues)

            # Display
            table = Table(show_header=False, show_edge=False)
            table.add_column("Metric", style="cyan", width=20)
            table.add_column("Value", width=40)
            table.add_row("Rows", str(rows))
            table.add_row("Duplicates", str(duplicates))
            table.add_row("Out-of-Order", str(out_of_order))
            table.add_row("Zero Volume", str(zero_volume))
            table.add_row("Schema", "PASS" if schema_ok else "FAIL")
            table.add_row("Completeness", f"{completeness:.1f}%")
            table.add_row("Latency", f"{latency:.0f}ms")
            table.add_row("Status", status)
            console.print(table)

        except Exception as e:
            console.print(f"  ERROR: {e}")
