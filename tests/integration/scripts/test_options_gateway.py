#!/usr/bin/env python3
"""Test options contracts using gateway interface.

Tests both Dhan and Upstox brokers through their standard gateway
``options`` facade (added so CLI/tests no longer reach into broker internals).
Uses the project venv: /Users/apple/Downloads/Trade_XV2/venv/bin/python

Usage:
    /Users/apple/Downloads/Trade_XV2/venv/bin/python test_options_gateway.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from rich.console import Console
from rich.table import Table

console = Console()


def test_dhan_options_via_gateway():
    """Test Dhan options through the gateway.options facade."""
    console.print("\n[bold cyan]" + "=" * 60)
    console.print("[bold]Testing DHAN OPTIONS (via Gateway)[/bold]")
    console.print("=" * 60)

    try:
        import time

        from infrastructure.gateway.factory import bootstrap_gateway
        from infrastructure.io.environment_bootstrap import load_env_file

        env_path = Path(".env.local")
        if not env_path.exists():
            console.print(f"[yellow]Skipping: {env_path} not found[/yellow]")
            return False
        load_env_file(env_path)

        console.print("\n[cyan]Creating Dhan gateway...[/cyan]")
        t0 = time.time()
        boot = bootstrap_gateway(
            "dhan",
            env_path=env_path,
            load_instruments=True,
            require_authenticated=True,
        )
        gw = boot.gateway if boot.live_ready else None
        latency = (time.time() - t0) * 1000
        if not gw:
            console.print("[red]Gateway creation failed[/red]")
            return False
        console.print(f"[green]Gateway created ({latency:.0f}ms)[/green]")

        results = {}

        # 1. Expiries
        console.print("\n[cyan]1. Getting NIFTY Option Expiries...[/cyan]")
        try:
            t0 = time.time()
            expiries = gw.options.get_expiries("NIFTY", "INDEX")
            latency = (time.time() - t0) * 1000
            console.print(f"[green]Found {len(expiries)} expiries ({latency:.0f}ms)[/green]")
            for e in expiries[:3]:
                console.print(f"  {e}")
            results["expiries"] = {
                "status": "PASS",
                "count": len(expiries),
                "latency_ms": latency,
                "nearest": expiries[0] if expiries else None,
            }
        except Exception as e:
            console.print(f"[red]Failed: {e}[/red]")
            results["expiries"] = {"status": "FAIL", "error": str(e)[:100]}

        # 2. Chain (canonical shape: {strikes: [{strike, call, put}]})
        console.print("\n[cyan]2. Getting NIFTY Option Chain...[/cyan]")
        try:
            if results["expiries"]["status"] == "PASS" and results["expiries"].get("count", 0) > 0:
                t0 = time.time()
                expiry = results["expiries"]["nearest"]
                chain = gw.options.get_option_chain("NIFTY", "INDEX", expiry)
                latency = (time.time() - t0) * 1000

                strikes = chain.get("strikes", []) if isinstance(chain, dict) else []
                console.print(f"[green]Chain: {len(strikes)} strikes ({latency:.0f}ms)[/green]")
                for s in strikes[:3]:
                    if not isinstance(s, dict):
                        continue
                    ce = s.get("call", {}) or {}
                    pe = s.get("put", {}) or {}
                    ce_sym = ce.get("trading_symbol") or ce.get("symbol") or "N/A"
                    pe_sym = pe.get("trading_symbol") or pe.get("symbol") or "N/A"
                    console.print(
                        f"  strike={s.get('strike')} CE={ce_sym} (ltp={ce.get('ltp')})"
                        f" PE={pe_sym} (ltp={pe.get('ltp')})"
                    )
                results["chain"] = {"status": "PASS", "count": len(strikes), "latency_ms": latency}
            else:
                console.print("[yellow]Skipping - no expiries[/yellow]")
                results["chain"] = {"status": "SKIP"}
        except Exception as e:
            console.print(f"[red]Failed: {e}[/red]")
            results["chain"] = {"status": "FAIL", "error": str(e)[:100]}

        # 3. Contract quote (best effort, requires a tradable CE symbol)
        console.print("\n[cyan]3. Testing Option Contract Quote...[/cyan]")
        try:
            if results["chain"]["status"] == "PASS" and results["chain"].get("count", 0) > 0:
                expiry = results["expiries"]["nearest"]
                chain = gw.options.get_option_chain("NIFTY", "INDEX", expiry)
                strikes = chain.get("strikes", []) if isinstance(chain, dict) else []
                first_ce = next(
                    (s["call"] for s in strikes if isinstance(s, dict) and s.get("call")),
                    None,
                )
                if first_ce:
                    symbol = first_ce.get("trading_symbol") or first_ce.get("symbol")
                    if symbol:
                        console.print(f"  Testing quote for: {symbol}")
                        t0 = time.time()
                        quote = gw.quote(symbol, "NFO")
                        latency = (time.time() - t0) * 1000
                        console.print(
                            f"[green]Quote: LTP=Rs.{quote.ltp}, "
                            f"Volume={quote.volume:,} ({latency:.0f}ms)[/green]"
                        )
                        results["contract_quote"] = {
                            "status": "PASS",
                            "ltp": quote.ltp,
                            "volume": quote.volume,
                            "latency_ms": latency,
                        }
                    else:
                        results["contract_quote"] = {"status": "SKIP", "reason": "no symbol"}
                else:
                    results["contract_quote"] = {"status": "SKIP", "reason": "no CE leg"}
            else:
                results["contract_quote"] = {"status": "SKIP"}
        except Exception as e:
            console.print(f"[red]Failed: {e}[/red]")
            results["contract_quote"] = {"status": "FAIL", "error": str(e)[:100]}

        gw.close()
        _print_summary("Dhan Options", results)
        return _all_pass_or_skip(results)
    except Exception as e:
        console.print(f"[red]Test failed: {e}[/red]")
        import traceback

        console.print(traceback.format_exc())
        return False


def test_upstox_options_via_gateway():
    """Test Upstox options through the gateway.options facade."""
    console.print("\n[bold cyan]" + "=" * 60)
    console.print("[bold]Testing UPSTOX OPTIONS (via Gateway)[/bold]")
    console.print("=" * 60)

    try:
        import time

        from infrastructure.gateway.factory import bootstrap_gateway
        from infrastructure.io.environment_bootstrap import load_env_file

        env_path = Path(".env.upstox")
        if not env_path.exists():
            console.print(f"[yellow]Skipping: {env_path} not found[/yellow]")
            return False
        load_env_file(env_path)

        console.print("\n[cyan]Creating Upstox gateway...[/cyan]")
        t0 = time.time()
        boot = bootstrap_gateway(
            "upstox",
            env_path=env_path,
            load_instruments=True,
            require_authenticated=True,
        )
        gw = boot.gateway if boot.live_ready else None
        latency = (time.time() - t0) * 1000
        if not gw:
            console.print("[red]Gateway creation failed[/red]")
            return False
        console.print(f"[green]Gateway created ({latency:.0f}ms)[/green]")

        if not hasattr(gw, "options"):
            console.print("[red]No options facade on gateway[/red]")
            gw.close()
            return False

        results = {}

        # 1. Expiries (derived from in-memory instrument master)
        console.print("\n[cyan]1. Getting NIFTY Option Expiries...[/cyan]")
        try:
            t0 = time.time()
            expiries = gw.options.get_expiries("NIFTY", "INDEX")
            latency = (time.time() - t0) * 1000
            console.print(f"[green]Found {len(expiries)} expiries ({latency:.0f}ms)[/green]")
            for e in expiries[:3]:
                console.print(f"  {e}")
            results["expiries"] = {
                "status": "PASS",
                "count": len(expiries),
                "latency_ms": latency,
                "nearest": expiries[0] if expiries else None,
            }
        except Exception as e:
            console.print(f"[red]Failed: {e}[/red]")
            results["expiries"] = {"status": "FAIL", "error": str(e)[:100]}

        # 2. Chain
        console.print("\n[cyan]2. Getting NIFTY Option Chain...[/cyan]")
        try:
            if results["expiries"]["status"] == "PASS" and results["expiries"].get("count", 0) > 0:
                t0 = time.time()
                expiry = results["expiries"]["nearest"]
                chain = gw.options.get_option_chain("NIFTY", "INDEX", expiry)
                latency = (time.time() - t0) * 1000
                strikes = chain.get("strikes", []) if isinstance(chain, dict) else []
                console.print(f"[green]Chain: {len(strikes)} strikes ({latency:.0f}ms)[/green]")
                for s in strikes[:3]:
                    if not isinstance(s, dict):
                        continue
                    ce = s.get("call", {}) or {}
                    pe = s.get("put", {}) or {}
                    ce_sym = ce.get("trading_symbol") or ce.get("symbol") or "N/A"
                    pe_sym = pe.get("trading_symbol") or pe.get("symbol") or "N/A"
                    console.print(
                        f"  strike={s.get('strike')} CE={ce_sym} (ltp={ce.get('ltp')})"
                        f" PE={pe_sym} (ltp={pe.get('ltp')})"
                    )
                results["chain"] = {"status": "PASS", "count": len(strikes), "latency_ms": latency}
            else:
                console.print("[yellow]Skipping - no expiries[/yellow]")
                results["chain"] = {"status": "SKIP"}
        except Exception as e:
            console.print(f"[red]Failed: {e}[/red]")
            results["chain"] = {"status": "FAIL", "error": str(e)[:100]}

        gw.close()
        _print_summary("Upstox Options", results)
        return _all_pass_or_skip(results)
    except Exception as e:
        console.print(f"[red]Test failed: {e}[/red]")
        import traceback

        console.print(traceback.format_exc())
        return False


def _print_summary(name: str, results: dict) -> None:
    console.print(f"\n[bold]{name} Summary:[/bold]")
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Test", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Details")
    for test_name, result in results.items():
        if isinstance(result, dict):
            status = result.get("status", "N/A")
            details = ", ".join(
                f"{k}={v}" for k, v in result.items() if k not in ("status", "error")
            )
            if "error" in result:
                details = result["error"][:50]
        else:
            status = "PASS" if result else "FAIL"
            details = str(result)
        style = "green" if status == "PASS" else "yellow" if status == "SKIP" else "red"
        table.add_row(test_name.upper(), f"[{style}]{status}[/{style}]", str(details)[:60])
    console.print(table)


def _all_pass_or_skip(results: dict) -> bool:
    return all(
        r.get("status") in ("PASS", "SKIP") if isinstance(r, dict) else r for r in results.values()
    )


if __name__ == "__main__":
    console.print("[bold]Testing Options Contracts via Gateway[/bold]")
    console.print(f"Python: {sys.version}")
    console.print(f"Date: {__import__('datetime').date.today().isoformat()}")

    dhan_ok = test_dhan_options_via_gateway()
    upstox_ok = test_upstox_options_via_gateway()

    console.print("\n\n" + "=" * 60)
    console.print("[bold]OVERALL SUMMARY[/bold]")
    console.print("=" * 60)
    console.print(f"\nDhan Options:   {'PASS' if dhan_ok else 'FAIL'}")
    console.print(f"Upstox Options: {'PASS' if upstox_ok else 'FAIL'}")
    if dhan_ok and upstox_ok:
        console.print("\n[bold green]All options tests passed[/bold green]")
    else:
        console.print("\n[bold yellow]Some tests failed - see details above[/bold yellow]")
    console.print("=" * 60)
