#!/usr/bin/env python3
"""Test options chain and contract details for both brokers.

Runs against real Upstox/Dhan APIs. Skips a broker if its env file is
absent or credentials are missing.

Usage:
    /Users/apple/Downloads/Trade_XV2/venv/bin/python test_options_contracts.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import contextlib

from rich.console import Console
from rich.table import Table

console = Console()


def _test_broker_options(
    name: str, env_filename: str, symbol: str = "NIFTY", exchange: str = "INDEX"
) -> bool:
    console.print("\n[bold cyan]" + "=" * 60)
    console.print(f"[bold]Testing {name} options[/bold]")
    console.print("=" * 60)

    env_path = Path(env_filename)
    if not env_path.exists():
        console.print(f"[yellow]Skipping {name}: {env_filename} not found[/yellow]")
        return False

    from infrastructure.gateway.factory import bootstrap_gateway
    from infrastructure.io.environment_bootstrap import load_env_file

    load_env_file(env_path)

    boot = bootstrap_gateway(
        name,
        env_path=env_path,
        load_instruments=True,
        require_authenticated=True,
    )
    gw = boot.gateway if boot.live_ready else None
    if gw is None:
        console.print(f"[red]Failed to create {name} gateway[/red]")
        return False

    console.print(f"[green]{name} gateway created[/green]")
    results = {}

    try:
        if not hasattr(gw, "options"):
            console.print(f"[red]{name}: no options facade on gateway[/red]")
            return False

        # 1. Expiries
        try:
            expiries = gw.options.get_expiries(symbol, exchange)
            console.print(f"[green]Expiries: {len(expiries)} found[/green]")
            for e in expiries[:3]:
                console.print(f"  {e}")
            results["expiries"] = {"status": "PASS", "count": len(expiries)}
        except Exception as exc:
            console.print(f"[red]Expiries failed: {exc}[/red]")
            results["expiries"] = {"status": "FAIL", "error": str(exc)[:100]}

        # 2. Chain
        try:
            chain = gw.options.get_option_chain(symbol, exchange)
            strikes = chain.get("strikes", []) if isinstance(chain, dict) else []
            console.print(
                f"[green]Chain: {len(strikes)} strikes (expiry={chain.get('expiry')})[/green]"
            )
            for strike in strikes[:3]:
                ce = strike.get("call", {}) if isinstance(strike, dict) else {}
                pe = strike.get("put", {}) if isinstance(strike, dict) else {}
                ce_sym = ce.get("trading_symbol") or ce.get("symbol") or "?"
                pe_sym = pe.get("trading_symbol") or pe.get("symbol") or "?"
                console.print(
                    f"  strike={strike.get('strike')} CE={ce_sym} (ltp={ce.get('ltp')})"
                    f" PE={pe_sym} (ltp={pe.get('ltp')})"
                )
            results["chain"] = {"status": "PASS", "count": len(strikes)}
        except Exception as exc:
            console.print(f"[red]Chain failed: {exc}[/red]")
            results["chain"] = {"status": "FAIL", "error": str(exc)[:100]}

        # 3. Per-leg contract quote (best effort)
        try:
            if (
                results.get("chain", {}).get("status") == "PASS"
                and results["chain"].get("count", 0) > 0
            ):
                first_ce = strikes[0].get("call", {})
                ce_sym = first_ce.get("trading_symbol") or first_ce.get("symbol")
                if ce_sym:
                    quote = gw.quote(ce_sym, "NFO")
                    console.print(
                        f"[green]Quote: {ce_sym} ltp={quote.ltp} vol={quote.volume}[/green]"
                    )
                    results["contract_quote"] = {"status": "PASS", "ltp": float(quote.ltp)}
                else:
                    results["contract_quote"] = {
                        "status": "SKIP",
                        "reason": "no CE symbol on chain",
                    }
            else:
                results["contract_quote"] = {"status": "SKIP"}
        except Exception as exc:
            console.print(f"[red]Contract quote failed: {exc}[/red]")
            results["contract_quote"] = {"status": "FAIL", "error": str(exc)[:100]}

        # Summary table
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Test")
        table.add_column("Status")
        table.add_column("Details")
        for test_name, result in results.items():
            status = result.get("status", "N/A") if isinstance(result, dict) else str(result)
            details = (
                ", ".join(f"{k}={v}" for k, v in result.items() if k != "status" and k != "error")
                if isinstance(result, dict)
                else ""
            )
            style = "green" if status == "PASS" else "yellow" if status == "SKIP" else "red"
            table.add_row(test_name.upper(), f"[{style}]{status}[/{style}]", details[:60])
        console.print(table)
        return all(
            r.get("status") in ["PASS", "SKIP"] if isinstance(r, dict) else r
            for r in results.values()
        )
    finally:
        with contextlib.suppress(Exception):
            gw.close()


if __name__ == "__main__":
    dhan_ok = _test_broker_options("dhan", ".env.local")
    upstox_ok = _test_broker_options("upstox", ".env.upstox")
    console.print("\n" + "=" * 60)
    console.print(f"Dhan:     {'PASS' if dhan_ok else 'FAIL'}")
    console.print(f"Upstox:   {'PASS' if upstox_ok else 'FAIL'}")
    console.print("=" * 60)
