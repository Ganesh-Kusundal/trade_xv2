#!/usr/bin/env python3
"""Test all broker connections with real API calls.

Tests both Dhan and Upstox brokers using actual credentials from .env files.
Uses the project's venv for execution.

Usage:
    python test_broker_connections.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402

console = Console()


def test_dhan_connection() -> dict:
    """Test Dhan broker connection with real API calls."""
    results = {}

    console.print("\n[bold cyan]═" * 60)
    console.print("[bold]🔵 TESTING DHAN BROKER CONNECTION[/bold]")
    console.print("[bold cyan]═" * 60)

    try:
        from brokers.common.env_loader import load_env_file
        from cli.services.broker_registry import bootstrap_gateway

        # Load .env.local
        env_path = PROJECT_ROOT / ".env.local"
        if not env_path.exists():
            console.print("[red]✗ .env.local not found[/red]")
            return {"status": "FAIL", "error": ".env.local not found"}

        load_env_file(env_path)
        console.print("[dim]✓ Loaded .env.local[/dim]")

        # Create gateway
        console.print("\n[cyan]Creating Dhan gateway...[/cyan]")
        t0 = time.time()
        try:
            bootstrap = bootstrap_gateway(
                "dhan",
                env_path=env_path,
                load_instruments=True,
                require_authenticated=True,
            )
        except Exception as e:
            console.print(f"[red]✗ Dhan gateway creation failed: {e}[/red]")
            console.print(
                "[yellow]⚠ Dhan broker package may not be installed. Run: pip install dhanhq[/yellow]"
            )
            return {"gateway_creation": {"status": "FAIL", "error": str(e)}}

        latency = (time.time() - t0) * 1000

        if not bootstrap.live_ready or bootstrap.gateway is None:
            console.print(
                f"[red]✗ Dhan bootstrap failed: status={bootstrap.status.value} "
                f"error={bootstrap.error}[/red]"
            )
            return {
                "status": "FAIL",
                "error": bootstrap.error or bootstrap.status.value,
                "bootstrap_status": bootstrap.status.value,
            }

        gateway = bootstrap.gateway
        console.print(
            f"[green]✓ Dhan gateway ready ({latency:.0f}ms) "
            f"status={bootstrap.status.value} probe={bootstrap.probe_name} "
            f"refreshed={bootstrap.refreshed_token}[/green]"
        )
        results["gateway_creation"] = {"status": "PASS", "latency_ms": latency}

        # Test 1: Portfolio/Balance
        console.print("\n[cyan]1. Testing Portfolio/Balance...[/cyan]")
        try:
            t0 = time.time()
            # Dhan uses 'funds' method, Upstox uses 'portfolio' property
            if hasattr(gateway, "portfolio"):
                balance = gateway.portfolio.get_balance()
            elif hasattr(gateway, "funds"):
                balance = gateway.funds()  # Call the method
            else:
                raise AttributeError("No portfolio or funds attribute found")

            latency = (time.time() - t0) * 1000
            console.print(
                f"[green]✓ Balance: ₹{balance.available_balance:.2f} ({latency:.0f}ms)[/green]"
            )
            results["portfolio"] = {
                "status": "PASS",
                "available_balance": balance.available_balance,
                "latency_ms": latency,
            }
        except Exception as e:
            console.print(f"[red]✗ Portfolio test failed: {e}[/red]")
            results["portfolio"] = {"status": "FAIL", "error": str(e)}

        # Test 2: Quote (RELIANCE)
        console.print("\n[cyan]2. Testing Quote (RELIANCE)...[/cyan]")
        try:
            t0 = time.time()
            quote = gateway.quote("RELIANCE", "NSE")
            latency = (time.time() - t0) * 1000
            console.print(
                f"[green]✓ RELIANCE LTP: ₹{quote.ltp}, Volume: {quote.volume:,} ({latency:.0f}ms)[/green]"
            )
            results["quote"] = {
                "status": "PASS",
                "ltp": quote.ltp,
                "volume": quote.volume,
                "latency_ms": latency,
            }
        except Exception as e:
            console.print(f"[red]✗ Quote test failed: {e}[/red]")
            results["quote"] = {"status": "FAIL", "error": str(e)}

        # Test 3: Historical Data
        console.print("\n[cyan]3. Testing Historical Data (RELIANCE, 1D, 30 days)...[/cyan]")
        try:
            t0 = time.time()
            df = gateway.history("RELIANCE", timeframe="1D", lookback_days=30)
            latency = (time.time() - t0) * 1000
            rows = len(df)
            console.print(f"[green]✓ Historical: {rows} candles ({latency:.0f}ms)[/green]")
            results["historical"] = {"status": "PASS", "rows": rows, "latency_ms": latency}
        except Exception as e:
            console.print(f"[red]✗ Historical test failed: {e}[/red]")
            results["historical"] = {"status": "FAIL", "error": str(e)}

        # Test 4: Market Depth
        console.print("\n[cyan]4. Testing Market Depth (RELIANCE)...[/cyan]")
        try:
            t0 = time.time()
            depth = gateway.depth("RELIANCE", "NSE")
            latency = (time.time() - t0) * 1000
            bids = len(depth.bids) if depth.bids else 0
            asks = len(depth.asks) if depth.asks else 0
            console.print(f"[green]✓ Depth: {bids} bids, {asks} asks ({latency:.0f}ms)[/green]")
            results["depth"] = {"status": "PASS", "bids": bids, "asks": asks, "latency_ms": latency}
        except Exception as e:
            console.print(f"[red]✗ Depth test failed: {e}[/red]")
            results["depth"] = {"status": "FAIL", "error": str(e)}

        # Test 5: Options (NIFTY) - check if available
        console.print("\n[cyan]5. Testing Options (NIFTY expiries)...[/cyan]")
        try:
            if hasattr(gateway, "options"):
                t0 = time.time()
                expiries = gateway.options.get_expiries("NIFTY", "INDEX")
                latency = (time.time() - t0) * 1000
                console.print(
                    f"[green]✓ NIFTY Options: {len(expiries)} expiries ({latency:.0f}ms)[/green]"
                )
                results["options"] = {
                    "status": "PASS",
                    "expiries": len(expiries),
                    "latency_ms": latency,
                }
            elif hasattr(gateway, "extended"):
                # Dhan uses extended capabilities for options
                console.print(
                    "[yellow]⚠ Options via extended capabilities (testing future_chain)...[/yellow]"
                )
                try:
                    t0 = time.time()
                    contracts = gateway.future_chain("NIFTY", "NSE")
                    latency = (time.time() - t0) * 1000
                    console.print(
                        f"[green]✓ NIFTY Futures: {len(contracts)} contracts ({latency:.0f}ms)[/green]"
                    )
                    results["options"] = {
                        "status": "PASS",
                        "contracts": len(contracts),
                        "latency_ms": latency,
                        "note": "Using future_chain instead of options.get_expiries",
                    }
                except Exception as e:
                    console.print(f"[yellow]⚠ Extended options test skipped: {e}[/yellow]")
                    results["options"] = {
                        "status": "SKIP",
                        "reason": "Not available via standard interface",
                    }
            else:
                console.print("[yellow]⚠ Options API not available[/yellow]")
                results["options"] = {"status": "SKIP", "reason": "Not available"}
        except Exception as e:
            console.print(f"[red]✗ Options test failed: {e}[/red]")
            results["options"] = {"status": "FAIL", "error": str(e)}

        # Close gateway
        gateway.close()
        console.print("\n[dim]✓ Dhan gateway closed[/dim]")

        return results

    except Exception as e:
        console.print(f"[red]✗ Dhan connection test failed: {e}[/red]")
        import traceback

        console.print(traceback.format_exc())
        return {"status": "FAIL", "error": str(e)}


def test_upstox_connection() -> dict:
    """Test Upstox broker connection with real API calls."""
    results = {}

    console.print("\n[bold cyan]═" * 60)
    console.print("[bold]🟡 TESTING UPSTOX BROKER CONNECTION[/bold]")
    console.print("[bold cyan]═" * 60)

    try:
        from brokers.common.env_loader import load_env_file
        from cli.services.broker_registry import bootstrap_gateway

        # Load .env.upstox
        env_path = PROJECT_ROOT / ".env.upstox"
        if not env_path.exists():
            console.print("[red]✗ .env.upstox not found[/red]")
            return {"status": "FAIL", "error": ".env.upstox not found"}

        load_env_file(env_path)
        console.print("[dim]✓ Loaded .env.upstox[/dim]")

        # Create gateway
        console.print("\n[cyan]Creating Upstox gateway...[/cyan]")
        t0 = time.time()
        bootstrap = bootstrap_gateway(
            "upstox",
            env_path=env_path,
            load_instruments=True,
            require_authenticated=True,
        )
        latency = (time.time() - t0) * 1000

        if not bootstrap.live_ready or bootstrap.gateway is None:
            console.print(
                f"[red]✗ Upstox bootstrap failed: status={bootstrap.status.value} "
                f"error={bootstrap.error}[/red]"
            )
            return {
                "status": "FAIL",
                "error": bootstrap.error or bootstrap.status.value,
                "bootstrap_status": bootstrap.status.value,
            }

        gateway = bootstrap.gateway
        console.print(
            f"[green]✓ Upstox gateway ready ({latency:.0f}ms) "
            f"status={bootstrap.status.value} probe={bootstrap.probe_name} "
            f"refreshed={bootstrap.refreshed_token}[/green]"
        )
        results["gateway_creation"] = {"status": "PASS", "latency_ms": latency}

        # Test 1: Portfolio/Balance (check if available)
        console.print("\n[cyan]1. Testing Portfolio/Balance...[/cyan]")
        try:
            if hasattr(gateway, "portfolio"):
                t0 = time.time()
                balance = gateway.portfolio.get_balance()
                latency = (time.time() - t0) * 1000
                console.print(
                    f"[green]✓ Balance: ₹{balance.available_balance:.2f} ({latency:.0f}ms)[/green]"
                )
                results["portfolio"] = {
                    "status": "PASS",
                    "available_balance": balance.available_balance,
                    "latency_ms": latency,
                }
            else:
                console.print(
                    "[yellow]⚠ Portfolio API not available on Upstox gateway (analytics-only mode)[/yellow]"
                )
                results["portfolio"] = {
                    "status": "SKIP",
                    "reason": "Not available in analytics-only mode",
                }
        except Exception as e:
            console.print(f"[red]✗ Portfolio test failed: {e}[/red]")
            results["portfolio"] = {"status": "FAIL", "error": str(e)}

        # Test 2: Quote (RELIANCE)
        console.print("\n[cyan]2. Testing Quote (RELIANCE)...[/cyan]")
        try:
            t0 = time.time()
            quote = gateway.quote("RELIANCE", "NSE_EQ")
            latency = (time.time() - t0) * 1000
            console.print(
                f"[green]✓ RELIANCE LTP: ₹{quote.ltp}, Volume: {quote.volume:,} ({latency:.0f}ms)[/green]"
            )
            results["quote"] = {
                "status": "PASS",
                "ltp": quote.ltp,
                "volume": quote.volume,
                "latency_ms": latency,
            }
        except Exception as e:
            console.print(f"[red]✗ Quote test failed: {e}[/red]")
            results["quote"] = {"status": "FAIL", "error": str(e)}

        # Test 3: Historical Data
        console.print("\n[cyan]3. Testing Historical Data (RELIANCE, 1D, 30 days)...[/cyan]")
        try:
            t0 = time.time()
            df = gateway.history("RELIANCE", timeframe="1D", lookback_days=30)
            latency = (time.time() - t0) * 1000
            rows = len(df)
            console.print(f"[green]✓ Historical: {rows} candles ({latency:.0f}ms)[/green]")
            results["historical"] = {"status": "PASS", "rows": rows, "latency_ms": latency}
        except Exception as e:
            console.print(f"[red]✗ Historical test failed: {e}[/red]")
            results["historical"] = {"status": "FAIL", "error": str(e)}

        # Test 4: Market Depth
        console.print("\n[cyan]4. Testing Market Depth (RELIANCE)...[/cyan]")
        try:
            t0 = time.time()
            depth = gateway.depth("RELIANCE", "NSE_EQ")
            latency = (time.time() - t0) * 1000
            bids = len(depth.bids) if depth.bids else 0
            asks = len(depth.asks) if depth.asks else 0
            console.print(f"[green]✓ Depth: {bids} bids, {asks} asks ({latency:.0f}ms)[/green]")
            results["depth"] = {"status": "PASS", "bids": bids, "asks": asks, "latency_ms": latency}
        except Exception as e:
            console.print(f"[red]✗ Depth test failed: {e}[/red]")
            results["depth"] = {"status": "FAIL", "error": str(e)}

        # Close gateway
        gateway.close()
        console.print("\n[dim]✓ Upstox gateway closed[/dim]")

        return results

    except Exception as e:
        console.print(f"[red]✗ Upstox connection test failed: {e}[/red]")
        import traceback

        console.print(traceback.format_exc())
        return {"status": "FAIL", "error": str(e)}


def print_summary(dhan_results: dict, upstox_results: dict) -> None:
    """Print summary table of all tests."""
    console.print("\n\n" + "=" * 80)
    console.print("[bold]📊 BROKER CONNECTION TEST SUMMARY[/bold]")
    console.print("=" * 80)

    # Dhan Summary
    console.print("\n[bold blue]DHAN Results:[/bold blue]")
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Test", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Details")

    for test_name, result in dhan_results.items():
        if isinstance(result, str):
            # Handle error string
            status = "FAIL"
            details = result[:60]
        else:
            status = result.get("status", "N/A")
            details = ", ".join(
                f"{k}={v}" for k, v in result.items() if k not in ("status", "error")
            )
            if "error" in result:
                details = result["error"][:60]

        style = "green" if status == "PASS" else "yellow" if status == "SKIP" else "red"
        table.add_row(test_name.upper(), f"[{style}]{status}[/{style}]", str(details)[:60])

    console.print(table)
    dhan_pass = sum(
        1 for r in dhan_results.values() if (isinstance(r, dict) and r.get("status") == "PASS")
    )
    dhan_total = len(dhan_results)
    console.print(f"\n[bold]Dhan: {dhan_pass}/{dhan_total} tests passed[/bold]")

    # Upstox Summary
    console.print("\n[bold yellow]UPSTOX Results:[/bold yellow]")
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Test", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Details")

    for test_name, result in upstox_results.items():
        if isinstance(result, str):
            # Handle error string
            status = "FAIL"
            details = result[:60]
        else:
            status = result.get("status", "N/A")
            details = ", ".join(
                f"{k}={v}" for k, v in result.items() if k not in ("status", "error")
            )
            if "error" in result:
                details = result["error"][:60]

        style = "green" if status == "PASS" else "yellow" if status == "SKIP" else "red"
        table.add_row(test_name.upper(), f"[{style}]{status}[/{style}]", str(details)[:60])

    console.print(table)
    upstox_pass = sum(
        1 for r in upstox_results.values() if (isinstance(r, dict) and r.get("status") == "PASS")
    )
    upstox_total = len(upstox_results)
    console.print(f"\n[bold]Upstox: {upstox_pass}/{upstox_total} tests passed[/bold]")

    # Overall
    console.print("\n" + "=" * 80)
    all_pass = (dhan_pass == dhan_total) and (upstox_pass == upstox_total)
    if all_pass:
        console.print("[bold green]✓ ALL BROKER CONNECTIONS WORKING CORRECTLY[/bold green]")
    else:
        console.print(
            "[bold yellow]⚠ SOME TESTS FAILED OR SKIPPED - CHECK DETAILS ABOVE[/bold yellow]"
        )
    console.print("=" * 80)


def main():
    """Run all broker connection tests."""
    console.print("[bold]🚀 Testing Broker Connections with Real API Calls[/bold]")
    console.print(f"[dim]Project Root: {PROJECT_ROOT}[/dim]")
    console.print(f"[dim]Python: {sys.version}[/dim]")

    # Test Dhan
    dhan_results = test_dhan_connection()

    # Test Upstox
    upstox_results = test_upstox_connection()

    # Print Summary
    print_summary(dhan_results, upstox_results)


if __name__ == "__main__":
    main()
