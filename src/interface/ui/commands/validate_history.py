"""CLI command for historical data quality validation."""

from __future__ import annotations

import time
from pathlib import Path

from domain.enums import BrokerId
from rich.console import Console
from rich.table import Table

from interface.ui.services.broker_ops import fetch_history_df


def run(args: list[str], broker_service, console: Console) -> None:
    """Validate historical data quality."""
    if not args:
        console.print("[yellow]Usage: tradex validate history <symbol>[/yellow]")
        return

    symbol = args[0].upper()
    console.print(f"\n[bold]Historical Data Quality: {symbol}[/bold]\n")

    for name, broker_id, env in [
        ("Dhan", BrokerId.DHAN, Path(".env.local")),
        ("Upstox", BrokerId.UPSTOX, Path(".env.upstox")),
    ]:
        console.print(f"\n[cyan]--- {name} ---[/cyan]")
        kw = {"env_path": str(env), "load_instruments": True}
        try:
            t0 = time.time()
            df = fetch_history_df(None, symbol, days=30, default=broker_id, **kw)
            latency = (time.time() - t0) * 1000

            rows = len(df)
            duplicates = (
                df.duplicated(subset=["timestamp"]).sum()
                if not df.empty and "timestamp" in df.columns
                else 0
            )
            schema_ok = "open" in getattr(df, "columns", []) and "close" in getattr(df, "columns", [])

            if not df.empty and "timestamp" in df.columns:
                out_of_order = (df["timestamp"].diff().dt.total_seconds() < 0).sum()
            else:
                out_of_order = 0

            if not df.empty and "timestamp" in df.columns:
                date_range = (df["timestamp"].max() - df["timestamp"].min()).days
                expected_candles = date_range * 5 / 7
                completeness = (rows / expected_candles * 100) if expected_candles > 0 else 100
            else:
                completeness = 0

            if not df.empty and "volume" in df.columns:
                zero_volume = (df["volume"] == 0).sum()
            else:
                zero_volume = 0

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
