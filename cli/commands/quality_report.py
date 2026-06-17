"""CLI command for data quality report."""

from __future__ import annotations

import time

from rich.console import Console
from rich.table import Table


def run(args: list[str], broker_service, console: Console) -> None:
    """Generate data quality report."""
    console.print("\n[bold]Data Quality Report[/bold]\n")

    # Get gateway
    try:
        from pathlib import Path

        from brokers.common.intelligent_gateway import IntelligentGateway
        from cli.services.broker_registry import create_gateway

        dhan = create_gateway("dhan", env_path=Path('.env.local'), load_instruments=True)
        upstox = create_gateway("upstox", env_path=Path('.env.upstox'), load_instruments=True)
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

    # Historical Quality — also capture quality data for overall score
    console.print("[cyan]Historical Data Quality[/cyan]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Broker", style="cyan")
    table.add_column("Quality", justify="right")
    table.add_column("Rows", justify="right")
    table.add_column("Duplicates", justify="right")
    table.add_column("Schema", justify="center")

    # Collect quality data for the overall score to avoid double-fetching
    quality_data: dict[str, dict] = {}

    for name, broker in [("Dhan", gw.dhan), ("Upstox", gw.upstox)]:
        if broker is None:
            table.add_row(name, "N/A", "-", "-", "-")
            continue
        try:
            df = broker.history('TCS', timeframe='1D', lookback_days=30)
            rows = len(df)
            duplicates = df.duplicated(subset=['timestamp']).sum() if not df.empty else 0
            expected_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi', 'symbol', 'exchange', 'timeframe']
            schema_ok = list(df.columns) == expected_cols
            missing = df.isnull().sum().sum() if not df.empty else 0
            quality = 100 - (duplicates / rows * 100) if rows > 0 else 0
            table.add_row(name, f"{quality:.2f}%", str(rows), str(duplicates), "PASS" if schema_ok else "FAIL")
            quality_data[name] = {
                "rows": rows, "duplicates": duplicates, "missing": missing,
                "quality": quality, "schema_ok": schema_ok,
            }
        except Exception as e:
            table.add_row(name, "ERROR", "-", "-", str(e)[:20])

    console.print(table)

    # Quote Quality
    console.print("\n[cyan]Quote Data Quality[/cyan]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Broker", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("LTP", justify="right")
    table.add_column("Volume", justify="right")

    for name, broker in [("Dhan", gw.dhan), ("Upstox", gw.upstox)]:
        try:
            q = broker.quote('TCS')
            table.add_row(name, "PASS", f"₹{q.ltp}", f"{q.volume:,}")
        except Exception as e:
            table.add_row(name, "ERROR", "-", str(e)[:20])

    console.print(table)

    # Option Chain Quality
    console.print("\n[cyan]Option Chain Quality[/cyan]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Broker", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Strikes", justify="right")
    table.add_column("Latency", justify="right")

    for name, broker in [("Dhan", gw.dhan)]:
        try:
            t0 = time.time()
            chain = broker.option_chain('NIFTY')
            latency = (time.time() - t0) * 1000
            strikes = len(chain.get('strikes', []))
            table.add_row(name, "PASS", str(strikes), f"{latency:.0f}ms")
        except Exception as e:
            table.add_row(name, "ERROR", "-", str(e)[:20])

    # Upstox
    table.add_row("Upstox", "N/A", "-", "deprecated")

    console.print(table)

    # Future Chain Quality
    console.print("\n[cyan]Future Chain Quality[/cyan]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Broker", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Contracts", justify="right")

    for name, broker in [("Dhan", gw.dhan)]:
        try:
            futures = broker.future_chain('NIFTY')
            contracts = len(futures.get('contracts', []))
            table.add_row(name, "PASS", str(contracts))
        except Exception as e:
            table.add_row(name, "ERROR", str(e)[:20])

    # Upstox
    table.add_row("Upstox", "N/A", "not supported")

    console.print(table)

    # Overall Score — reuses quality data already fetched in Historical Quality
    console.print("\n" + "="*50)
    console.print("[bold]OVERALL DATA QUALITY SCORE[/bold]")
    console.print("="*50)

    for broker_name, broker in [("Dhan", gw.dhan), ("Upstox", gw.upstox)]:
        if broker is None:
            console.print(f"  {broker_name}: Not configured")
            continue

        qd = quality_data.get(broker_name)
        if qd is None:
            console.print(f"  {broker_name}: Could not compute (see Historical Quality above)")
            continue

        # Detect capabilities (lightweight — only where historical already worked)
        capabilities = ["Historical"]
        try:
            broker.quote('TCS')
            capabilities.append("Quote")
        except Exception:
            pass
        try:
            broker.option_chain('NIFTY')
            capabilities.append("Option Chain")
        except Exception:
            pass
        try:
            broker.future_chain('NIFTY')
            capabilities.append("Futures")
        except Exception:
            pass

        console.print(f"  {broker_name}:")
        console.print(f"    Quality: {qd['quality']:.1f}% ({qd['rows']} rows, {qd['duplicates']} duplicates, {qd['missing']} missing)")
        console.print(f"    Schema: {'PASS' if qd['schema_ok'] else 'FAIL'}")
        console.print(f"    Capabilities: {', '.join(capabilities)}")

    console.print("  Recommendation: Use Dhan for complete data coverage")
