"""CLI command for data quality validation."""

from __future__ import annotations

import time

from rich.console import Console
from rich.table import Table


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

    # Get gateway
    try:
        from pathlib import Path

        from cli.services.broker_registry import create_gateway

        dhan = create_gateway("dhan", env_path=Path(".env.local"), load_instruments=True)
        if dhan:
            gw = dhan
        else:
            console.print("[red]No broker gateway available[/red]")
            return
    except Exception as e:
        console.print(f"[red]Error creating gateway: {e}[/red]")
        return

    results = {}

    # 1. Historical Validation
    console.print("[cyan]Testing Historical Data...[/cyan]")
    try:
        t0 = time.time()
        df = gw.history(symbol, timeframe="1D", lookback_days=30)
        latency = (time.time() - t0) * 1000

        rows = len(df)
        start_date = df["timestamp"].min() if not df.empty else None
        end_date = df["timestamp"].max() if not df.empty else None
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

        completeness = (
            ((rows / 22) * 100) if rows > 0 else 0
        )  # ~22 trading days in 30 calendar days

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
        q = gw.quote(symbol, exchange)
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
        q2 = gw.quote(symbol, exchange)
        ltp = q2.ltp
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
        d = gw.depth(symbol, exchange)
        latency = (time.time() - t0) * 1000

        bids = d.bids if d.bids else []
        asks = d.asks if d.asks else []
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
    """Validate broker connectivity using RELIANCE as test symbol."""
    symbol = "RELIANCE"
    for i, a in enumerate(args):
        if a == "--symbol" and i + 1 < len(args):
            symbol = args[i + 1].upper()
            break
        elif not a.startswith("--"):
            symbol = a.upper()
            break

    console.print(f"\n[bold]Validating broker with {symbol}...[/bold]\n")

    results = {}

    # 1. Historical Validation
    console.print("[cyan]Testing Historical Data...[/cyan]")
    try:
        from pathlib import Path

        from infrastructure.io.environment_bootstrap import load_env_file
        from cli.services.broker_registry import create_gateway

        env_path = Path(".env.local")
        if env_path.exists():
            load_env_file(env_path)
        gw = create_gateway("dhan", env_path=env_path, load_instruments=True)
        if not gw:
            console.print("[red]No broker gateway available[/red]")
            return

        t0 = time.time()
        df = gw.history(symbol, timeframe="1D", lookback_days=30)
        latency = (time.time() - t0) * 1000
        rows = len(df)
        results["historical"] = {"status": "PASS", "rows": rows, "latency": f"{latency:.0f}ms"}
        console.print(f"  Historical: PASS ({rows} candles, {latency:.0f}ms)")
    except Exception as e:
        results["historical"] = {"status": "ERROR", "error": str(e)}
        console.print(f"  Historical: ERROR - {e}")

    # 2. Quote
    console.print("[cyan]Testing Quote...[/cyan]")
    try:
        q = gw.quote(symbol, "NSE")
        results["quote"] = {"status": "PASS", "ltp": f"₹{q.ltp}", "volume": f"{q.volume:,}"}
        console.print(f"  Quote: PASS (LTP=₹{q.ltp}, Volume={q.volume:,})")
    except Exception as e:
        results["quote"] = {"status": "ERROR", "error": str(e)}
        console.print(f"  Quote: ERROR - {e}")

    # 3. Depth
    console.print("[cyan]Testing Depth...[/cyan]")
    try:
        d = gw.depth(symbol, "NSE")
        bids = d.bids if d.bids else []
        asks = d.asks if d.asks else []
        has_data = len(bids) > 0 or len(asks) > 0
        results["depth"] = {
            "status": "PASS" if has_data else "WARN",
            "bids": len(bids),
            "asks": len(asks),
        }
        console.print(
            f"  Depth: {'PASS' if has_data else 'WARN'} ({len(bids)} bids, {len(asks)} asks)"
        )
    except Exception as e:
        results["depth"] = {"status": "ERROR", "error": str(e)}
        console.print(f"  Depth: ERROR - {e}")

    # 4. Portfolio
    console.print("[cyan]Testing Portfolio...[/cyan]")
    try:
        bal = gw.portfolio.get_balance()
        results["portfolio"] = {"status": "PASS", "balance": f"₹{bal.available_balance}"}
        console.print(f"  Portfolio: PASS (Balance=₹{bal.available_balance})")
    except Exception as e:
        results["portfolio"] = {"status": "ERROR", "error": str(e)}
        console.print(f"  Portfolio: ERROR - {e}")

    # 5. Futures
    console.print("[cyan]Testing Futures...[/cyan]")
    try:
        fut = gw.futures.get_contracts("NIFTY", "INDEX")
        results["futures"] = {"status": "PASS", "contracts": len(fut)}
        console.print(f"  Futures: PASS ({len(fut)} NIFTY contracts)")
    except Exception as e:
        results["futures"] = {"status": "ERROR", "error": str(e)}
        console.print(f"  Futures: ERROR - {e}")

    # 6. Options
    console.print("[cyan]Testing Options...[/cyan]")
    try:
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

    gw.close()


def _run_data_validation(args: list[str], broker_service, console: Console) -> None:
    """Validate data quality of a CSV file."""
    from pathlib import Path

    import pandas as pd

    from tradex.runtime.services.data_validator import DataQualityValidator  # sanctioned — broker wiring layer

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

    validator = DataQualityValidator()
    report = validator.validate(df, symbol=symbol, timeframe=timeframe)

    # Print summary
    status_style = "green" if report.passed else "red"
    console.print(
        f"[bold {status_style}]Status: {'PASSED' if report.passed else 'FAILED'}[/bold {status_style}]"
    )
    console.print(f"Total rows: {report.total_rows}")
    console.print(
        f"Issues: {report.total_issues} (critical={report.critical_count}, warning={report.warning_count}, info={report.info_count})"
    )

    if report.issues:
        console.print("\n[bold]Issues:[/bold]")
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("#", style="dim", width=4)
        table.add_column("Severity", width=10)
        table.add_column("Category", width=12)
        table.add_column("Message")

        for i, issue in enumerate(report.issues[:30], 1):
            sev_style = {"critical": "red", "warning": "yellow", "info": "dim"}.get(
                issue.severity, ""
            )
            table.add_row(
                str(i),
                f"[{sev_style}]{issue.severity.upper()}[/{sev_style}]",
                issue.category,
                issue.message,
            )
        if len(report.issues) > 30:
            table.add_row("...", "", "", f"[dim]{len(report.issues) - 30} more issues[/dim]")
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
        from cli.services.broker_facade import DhanSymbolValidator

        validator = DhanSymbolValidator()
        result = validator.validate(symbol_str, exchange=exchange, segment=segment)
        import json

        console.print_json(json.dumps(result))
    except Exception as e:
        console.print(f"[red]Error performing symbol validation: {e}[/red]")
