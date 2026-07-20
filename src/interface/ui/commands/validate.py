"""CLI command for data quality validation."""

from __future__ import annotations

import time

from rich.console import Console
from rich.table import Table

from domain.enums import BrokerId


def run(args: list[str], broker_service, console: Console) -> None:
    """Validate data quality — broker health, symbol mapping, or CSV file."""
    if not args:
        console.print(
            "[yellow]Usage: tradex validate <symbol> OR tradex validate broker OR tradex validate symbol <symbol_string> OR tradex validate data <csv_file>[/yellow]"
        )
        return

    # Route subcommands
    if args[0].lower() == "data":
        _run_data_validation(args[1:], broker_service, console)
        return

    if args[0].lower() == "broker":
        _run_broker_validation(args[1:], broker_service, console)
        return

    if args[0].lower() == "symbol":
        _run_symbol_validation(args[1:], broker_service, console)
        return

    symbol = args[0].upper()
    exchange = "NSE"

    console.print(f"\n[bold]Validating {symbol}...[/bold]\n")

    from pathlib import Path

    from interface.ui.commands._broker import broker_id_from, history_as_df
    from interface.ui.services.broker_ops import get_depth, get_history, get_quote

    env = {"env_path": str(Path(".env.local")), "load_instruments": True}
    broker = broker_id_from(broker_service, default=BrokerId.DHAN)
    results = {}
    # 1. Historical Validation
    console.print("[cyan]Testing Historical Data...[/cyan]")
    try:
        t0 = time.time()
        df = history_as_df(get_history(broker, symbol, days=30, **env))
        latency = (time.time() - t0) * 1000

        rows = len(df)
        start_date = df["timestamp"].min() if not df.empty and "timestamp" in df.columns else None
        end_date = df["timestamp"].max() if not df.empty and "timestamp" in df.columns else None
        duplicates = (
            df.duplicated(subset=["timestamp"]).sum()
            if not df.empty and "timestamp" in df.columns
            else 0
        )
        schema_ok = "open" in df.columns and "close" in df.columns

        completeness = ((rows / 22) * 100) if rows > 0 else 0

        results["historical"] = {
            "status": "PASS" if schema_ok and duplicates == 0 else "FAIL",
            "rows": rows,
            "start": str(start_date)[:10] if start_date else "N/A",
            "end": str(end_date)[:10] if end_date else "N/A",
            "duplicates": duplicates,
            "schema": "PASS" if schema_ok else "FAIL",
            "completeness": f"{completeness:.0f}%",
            "latency": f"{latency:.0f}ms",
        }
        console.print(
            f"  Historical: {results['historical']['status']} ({rows} candles, {completeness:.0f}% complete)"
        )
    except Exception as e:
        results["historical"] = {"status": "ERROR", "error": str(e)}
        console.print(f"  Historical: ERROR - {e}")

    # 2. Quote Validation
    console.print("[cyan]Testing Quote...[/cyan]")
    try:
        t0 = time.time()
        q = get_quote(broker, symbol, exchange=exchange, **env)
        latency = (time.time() - t0) * 1000
        results["quote"] = {
            "status": "PASS",
            "ltp": f"₹{q.ltp}",
            "volume": f"{q.volume:,}",
            "latency": f"{latency:.0f}ms",
        }
        console.print(f"  Quote: PASS (LTP=₹{q.ltp}, Volume={q.volume:,})")
    except Exception as e:
        results["quote"] = {"status": "ERROR", "error": str(e)}
        console.print(f"  Quote: ERROR - {e}")

    # 3. LTP Validation
    console.print("[cyan]Testing LTP...[/cyan]")
    try:
        t0 = time.time()
        q = get_quote(broker, symbol, exchange=exchange, **env)
        ltp = q.ltp
        latency = (time.time() - t0) * 1000
        results["ltp"] = {"status": "PASS", "value": f"₹{ltp}", "latency": f"{latency:.0f}ms"}
        console.print(f"  LTP: PASS (₹{ltp})")
    except Exception as e:
        results["ltp"] = {"status": "ERROR", "error": str(e)}
        console.print(f"  LTP: ERROR - {e}")

    # 4. Depth Validation
    console.print("[cyan]Testing Depth...[/cyan]")
    try:
        t0 = time.time()
        d = get_depth(broker, symbol, exchange=exchange, **env)
        latency = (time.time() - t0) * 1000

        bids = d.bids if d and d.bids else []
        asks = d.asks if d and d.asks else []
        has_data = len(bids) > 0 or len(asks) > 0

        results["depth"] = {
            "status": "PASS" if has_data else "WARN",
            "bids": len(bids),
            "asks": len(asks),
            "latency": f"{latency:.0f}ms",
        }
        console.print(
            f"  Depth: {'PASS' if has_data else 'WARN'} ({len(bids)} bids, {len(asks)} asks)"
        )
    except Exception as e:
        results["depth"] = {"status": "ERROR", "error": str(e)}
        console.print(f"  Depth: ERROR - {e}")

    # 5. Summary
    console.print("\n" + "=" * 50)
    console.print("[bold]VALIDATION SUMMARY[/bold]")
    console.print("=" * 50)

    table = Table(show_header=True, header_style="bold")
    table.add_column("Check", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Details")

    for check, data in results.items():
        status = data.get("status", "N/A")
        style = "green" if status == "PASS" else "yellow" if status == "WARN" else "red"
        details = ", ".join(f"{k}={v}" for k, v in data.items() if k != "status" and k != "error")
        table.add_row(check.upper(), f"[{style}]{status}[/{style}]", details[:60])

    console.print(table)

    # Overall status
    all_pass = all(r.get("status") in ("PASS", "WARN") for r in results.values())
    if all_pass:
        console.print("\n[bold green]✓ ALL CHECKS PASSED[/bold green]")
    else:
        console.print("\n[bold red]✗ SOME CHECKS FAILED[/bold red]")


def _run_broker_validation(args: list[str], broker_service, console: Console) -> None:
    """Validate broker via brokers.services.run_verify."""
    broker = broker_service.active_broker_name if broker_service else BrokerId.DHAN
    for i, a in enumerate(args):
        if a == "--broker" and i + 1 < len(args):
            broker = args[i + 1].lower()
            break

    console.print(f"\n[bold]Validating broker ({broker}) via run_verify...[/bold]\n")
    from pathlib import Path

    from interface.ui.commands._broker import broker_id_from
    from runtime.platform_bridge import run_verify

    env = {"env_path": str(Path(".env.local")), "load_instruments": True}
    if broker == BrokerId.UPSTOX:
        env = {"env_path": str(Path(".env.upstox")), "load_instruments": True}

    try:
        report = run_verify(broker_id_from(broker_service, default=broker), **env)
    except Exception as exc:
        console.print(f"[red]Verify failed: {exc}[/red]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Step", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Detail")

    for step in report.steps:
        status = "PASS" if step.passed else "FAIL"
        style = "green" if step.passed else "red"
        table.add_row(step.name, f"[{style}]{status}[/{style}]", step.detail[:60])

    console.print(table)
    overall = "PASS" if report.passed else "FAIL"
    color = "green" if report.passed else "red"
    console.print(f"\n[bold {color}]Overall: {overall}[/bold {color}]")

    # Extended wire-only surfaces (futures/options listing) — keep gateway path
    from interface.ui.services.connect import connect_live

    env_path = Path(".env.local")
    results: dict[str, dict] = {}
    try:
        gw = connect_live(BrokerId.DHAN, env_path=env_path, load_instruments=True)
    except Exception:
        gw = None

    console.print("\n[cyan]Testing Futures (wire extension)...[/cyan]")
    try:
        if gw is None:
            raise RuntimeError("no gateway")
        fut = gw.futures.get_contracts("NIFTY", "INDEX")
        results["futures"] = {"status": "PASS", "contracts": len(fut)}
        console.print(f"  Futures: PASS ({len(fut)} NIFTY contracts)")
    except Exception as e:
        results["futures"] = {"status": "ERROR", "error": str(e)}
        console.print(f"  Futures: ERROR - {e}")

    # 6. Options
    console.print("[cyan]Testing Options...[/cyan]")
    try:
        if gw is None:
            raise RuntimeError("no gateway")
        exp = gw.options.get_expiries("NIFTY", "INDEX")
        results["options"] = {"status": "PASS", "expiries": len(exp)}
        console.print(f"  Options: PASS ({len(exp)} NIFTY expiries)")
    except Exception as e:
        results["options"] = {"status": "ERROR", "error": str(e)}
        console.print(f"  Options: ERROR - {e}")

    # Summary
    console.print("\n" + "=" * 50)
    console.print("[bold]BROKER VALIDATION SUMMARY[/bold]")
    console.print("=" * 50)

    table = Table(show_header=True, header_style="bold")
    table.add_column("Check", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Details")

    for check, data in results.items():
        status = data.get("status", "N/A")
        style = "green" if status == "PASS" else "yellow" if status == "WARN" else "red"
        details = ", ".join(f"{k}={v}" for k, v in data.items() if k not in ("status", "error"))
        table.add_row(check.upper(), f"[{style}]{status}[/{style}]", details[:60])

    console.print(table)

    all_pass = all(r.get("status") in ("PASS", "WARN") for r in results.values())
    if all_pass:
        console.print("\n[bold green]ALL CHECKS PASSED[/bold green]")
    else:
        console.print("\n[bold red]SOME CHECKS FAILED[/bold red]")

    if gw is not None:
        gw.close()


def _run_data_validation(args: list[str], broker_service, console: Console) -> None:
    """Validate data quality of a CSV file."""
    from pathlib import Path

    import pandas as pd

    from datalake.quality.validation import validate_candles

    if not args:
        console.print(
            "[yellow]Usage: tradex validate data <csv_file> [--timeframe 1d] [--symbol NIFTY][/yellow]"
        )
        console.print(
            "[dim]Example: tradex validate data data/nifty50_historical.csv --timeframe 1d --symbol NIFTY[/dim]"
        )
        return

    csv_path = Path(args[0])
    if not csv_path.exists():
        console.print(f"[red]File not found: {csv_path}[/red]")
        return

    # Parse optional flags
    timeframe = "1d"
    symbol = csv_path.stem
    for i, a in enumerate(args[1:], 1):
        if a == "--timeframe" and i + 1 < len(args):
            timeframe = args[i + 1]
        elif a == "--symbol" and i + 1 < len(args):
            symbol = args[i + 1]

    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        console.print(f"[red]Error reading CSV: {e}[/red]")
        return

    console.print(
        f"[bold]Validating {csv_path.name} ({len(df)} rows, timeframe={timeframe})...[/bold]\n"
    )

    _, audit = validate_candles(
        df, symbol=symbol, drop_invalid=False, return_audit=True, timeframe=timeframe
    )
    passed = audit.is_clean

    status_style = "green" if passed else "red"
    console.print(
        f"[bold {status_style}]Status: {'PASSED' if passed else 'FAILED'}[/bold {status_style}]"
    )
    console.print(f"Total rows: {audit.total_rows}")
    console.print(
        f"Valid rows: {audit.valid_rows}, dropped: {audit.dropped_rows}, issues: {len(audit.issues)}"
    )

    if audit.issues:
        console.print("\n[bold]Issues:[/bold]")
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("#", style="dim", width=4)
        table.add_column("Message")

        for i, issue in enumerate(audit.issues[:30], 1):
            table.add_row(str(i), issue)
        if len(audit.issues) > 30:
            table.add_row("...", f"[dim]{len(audit.issues) - 30} more issues[/dim]")
        console.print(table)
    else:
        console.print("\n[green]No issues found![/green]")


def _run_symbol_validation(args: list[str], broker_service, console: Console) -> None:
    """Validate a symbol's mapping to DhanHQ instruments and output as JSON."""
    if not args:
        console.print(
            "[yellow]Usage: tradex validate symbol <symbol_string> [--exchange <exchange>] [--segment <segment>][/yellow]"
        )
        return

    symbol_str = args[0]
    exchange = None
    segment = None

    # Parse arguments for optional filters
    i = 1
    while i < len(args):
        if args[i] == "--exchange" and i + 1 < len(args):
            exchange = args[i + 1]
            i += 2
        elif args[i] == "--segment" and i + 1 < len(args):
            segment = args[i + 1]
            i += 2
        else:
            i += 1

    try:
        from interface.ui.services.broker_registry import DhanSymbolValidator

        validator = DhanSymbolValidator()
        result = validator.validate(symbol_str, exchange=exchange, segment=segment)
        import json

        console.print_json(json.dumps(result))
    except Exception as e:
        console.print(f"[red]Error performing symbol validation: {e}[/red]")
