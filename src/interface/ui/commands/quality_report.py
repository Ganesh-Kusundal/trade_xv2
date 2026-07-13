"""CLI command for data quality report."""

from __future__ import annotations

import contextlib
import time
from pathlib import Path

from domain.enums import BrokerId
from rich.console import Console
from rich.table import Table

from interface.ui.services.broker_ops import fetch_history_df, fetch_option_chain, fetch_quote


def _env_kwargs(env: Path) -> dict:
    return {"env_path": str(env), "load_instruments": True}


def run(args: list[str], broker_service, console: Console) -> None:
    """Generate data quality report."""
    console.print("\n[bold]Data Quality Report[/bold]\n")

    brokers = [
        ("Dhan", BrokerId.DHAN, Path(".env.local")),
        ("Upstox", BrokerId.UPSTOX, Path(".env.upstox")),
    ]

    console.print("[cyan]Historical Data Quality[/cyan]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Broker", style="cyan")
    table.add_column("Quality", justify="right")
    table.add_column("Rows", justify="right")
    table.add_column("Duplicates", justify="right")
    table.add_column("Schema", justify="center")

    quality_data: dict[str, dict] = {}

    for name, broker_id, env in brokers:
        kw = _env_kwargs(env)
        try:
            df = fetch_history_df(None, "TCS", days=30, default=broker_id, **kw)
            rows = len(df)
            duplicates = (
                df.duplicated(subset=["timestamp"]).sum()
                if not df.empty and "timestamp" in df.columns
                else 0
            )
            schema_ok = "open" in df.columns and "close" in df.columns
            missing = df.isnull().sum().sum() if not df.empty else 0
            quality = 100 - (duplicates / rows * 100) if rows > 0 else 0
            table.add_row(
                name, f"{quality:.2f}%", str(rows), str(duplicates), "PASS" if schema_ok else "FAIL"
            )
            quality_data[name] = {
                "rows": rows,
                "duplicates": duplicates,
                "missing": missing,
                "quality": quality,
                "schema_ok": schema_ok,
            }
        except Exception as e:
            table.add_row(name, "ERROR", "-", "-", str(e)[:20])

    console.print(table)

    console.print("\n[cyan]Quote Data Quality[/cyan]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Broker", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("LTP", justify="right")
    table.add_column("Volume", justify="right")

    for name, broker_id, env in brokers:
        try:
            q = fetch_quote(None, "TCS", default=broker_id, **_env_kwargs(env))
            table.add_row(name, "PASS", f"₹{q.ltp}", f"{q.volume:,}")
        except Exception as e:
            table.add_row(name, "ERROR", "-", str(e)[:20])

    console.print(table)

    console.print("\n[cyan]Option Chain Quality[/cyan]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Broker", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Strikes", justify="right")
    table.add_column("Latency", justify="right")

    try:
        t0 = time.time()
        chain = fetch_option_chain(
            None, "NIFTY", default=BrokerId.DHAN, **_env_kwargs(Path(".env.local"))
        )
        latency = (time.time() - t0) * 1000
        strikes = len(getattr(chain, "strikes", []) or [])
        table.add_row("Dhan", "PASS", str(strikes), f"{latency:.0f}ms")
    except Exception as e:
        table.add_row("Dhan", "ERROR", "-", str(e)[:20])
    table.add_row("Upstox", "N/A", "-", "deprecated")
    console.print(table)

    console.print("\n" + "=" * 50)
    console.print("[bold]OVERALL DATA QUALITY SCORE[/bold]")
    console.print("=" * 50)

    for broker_name, broker_id, env in brokers:
        qd = quality_data.get(broker_name)
        if qd is None:
            console.print(f"  {broker_name}: Not configured")
            continue

        capabilities = ["Historical"]
        with contextlib.suppress(Exception):
            fetch_quote(None, "TCS", default=broker_id, **_env_kwargs(env))
            capabilities.append("Quote")

        console.print(f"  {broker_name}:")
        console.print(
            f"    Quality: {qd['quality']:.1f}% ({qd['rows']} rows, {qd['duplicates']} duplicates, {qd['missing']} missing)"
        )
        console.print(f"    Schema: {'PASS' if qd['schema_ok'] else 'FAIL'}")
        console.print(f"    Capabilities: {', '.join(capabilities)}")

    console.print("  Recommendation: Use Dhan for complete data coverage")
