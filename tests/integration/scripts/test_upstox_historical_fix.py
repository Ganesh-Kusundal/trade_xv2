#!/usr/bin/env python3
"""Regression test for Upstox historical API fix.

Tests that instrument keys are resolved correctly for different symbol types.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT))

from rich.console import Console

from infrastructure.config.env_loader import load_env_file

console = Console()


def _bootstrap_gateway(broker: str, env_path: Path):
    from infrastructure.gateway.factory import bootstrap_gateway

    result = bootstrap_gateway(
        broker,
        env_path=env_path,
        load_instruments=True,
        require_authenticated=True,
    )
    if not result.live_ready or result.gateway is None:
        return None
    return result.gateway


def test_instrument_key_resolution():
    """Test that symbol resolver returns correct instrument keys."""
    env_path = Path(".env.upstox")
    load_env_file(env_path)

    console.print("\n[bold]Test 1: Instrument Key Resolution[/bold]\n")

    gw = _bootstrap_gateway("upstox", env_path)
    if not gw:
        console.print("[red]✗ Gateway creation failed[/red]")
        return False

    resolver = gw._symbol_resolver

    test_cases = [
        # (symbol, exchange, expected_format, should_work)
        ("RELIANCE", "NSE", "ISIN", True),
        ("INFY", "NSE_EQ", "ISIN", True),
        ("NIFTY", "INDEX", "INDEX", True),
        ("BANKNIFTY", "INDEX", "INDEX", True),
    ]

    all_pass = True
    for symbol, exchange, expected_format, _should_work in test_cases:
        key = resolver.resolve_key(symbol, exchange)

        # Validate format
        if expected_format == "ISIN":
            # Should be segment|ISIN code (INE...)
            is_valid = "|" in key and "INE" in key
            status = "✓" if is_valid else "✗"
            console.print(f"{status} {symbol:15} ({exchange:10}) -> {key:35} (Expected ISIN)")
            if not is_valid:
                all_pass = False
        elif expected_format == "INDEX":
            # Should be NSE_INDEX|something
            is_valid = key.startswith("NSE_INDEX|")
            status = "✓" if is_valid else "✗"
            console.print(f"{status} {symbol:15} ({exchange:10}) -> {key:35} (Expected INDEX)")
            if not is_valid:
                all_pass = False

    gw.close()
    return all_pass


def test_historical_api():
    """Test historical API with resolved instrument keys."""
    env_path = Path(".env.upstox")
    load_env_file(env_path)

    console.print("\n[bold]Test 2: Historical API Calls[/bold]\n")

    gw = _bootstrap_gateway("upstox", env_path)
    if not gw:
        console.print("[red]✗ Gateway creation failed[/red]")
        return False

    test_cases = [
        # (symbol, exchange, description)
        ("RELIANCE", "NSE", "Equity with ISIN"),
        ("NIFTY", "INDEX", "Index symbol"),
    ]

    all_pass = True
    for symbol, exchange, description in test_cases:
        console.print(f"\n[cyan]{description}: {symbol} ({exchange})[/cyan]")
        try:
            df = gw.history(symbol, exchange, "1D", lookback_days=5)
            if len(df) > 0:
                console.print(f"  ✓ Success: {len(df)} candles")
            else:
                console.print("  ⚠ No data returned (market may be closed)")
        except Exception as e:
            error_msg = str(e)
            console.print(f"  ✗ Failed: {error_msg[:100]}")
            all_pass = False

    gw.close()
    return all_pass


def test_edge_cases():
    """Test edge cases that should produce warnings."""
    env_path = Path(".env.upstox")
    load_env_file(env_path)

    console.print("\n[bold]Test 3: Edge Cases (Should Warn)[/bold]\n")

    gw = _bootstrap_gateway("upstox", env_path)
    if not gw:
        console.print("[red]✗ Gateway creation failed[/red]")
        return False

    # This should produce a warning about space in symbol
    resolver = gw._symbol_resolver

    console.print("[yellow]Testing invalid symbol (should warn about space):[/yellow]")
    key = resolver.resolve_key("NIFTY 50", "NSE_EQ")
    console.print(f"  Result: {key}")

    if " " in key:
        console.print("  ⚠ Warning: Key contains space (expected for fallback)")

    gw.close()
    return True


if __name__ == "__main__":
    console.print("[bold]🧪 Upstox Historical API Regression Tests[/bold]\n")

    results = []

    results.append(("Instrument Key Resolution", test_instrument_key_resolution()))
    results.append(("Historical API Calls", test_historical_api()))
    results.append(("Edge Cases", test_edge_cases()))

    console.print("\n\n" + "=" * 60)
    console.print("[bold]TEST SUMMARY[/bold]")
    console.print("=" * 60)

    all_pass = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        style = "green" if passed else "red"
        console.print(f"[{style}]{status}[/{style}] {name}")
        if not passed:
            all_pass = False

    console.print("\n" + "=" * 60)
    if all_pass:
        console.print("[bold green]✅ ALL TESTS PASSED[/bold green]")
    else:
        console.print("[bold red]❌ SOME TESTS FAILED[/bold red]")
    console.print("=" * 60)

    sys.exit(0 if all_pass else 1)
