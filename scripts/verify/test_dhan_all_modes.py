"""Thin wrapper — delegates to the pytest suite.

The canonical source of truth is now:
    brokers/dhan/tests/regression/test_e2e_smoke.py

Running this script is equivalent to:
    pytest brokers/dhan/tests/regression/test_e2e_smoke.py -v

Kept for backward-compatibility with shell scripts and CI pipelines that call
it directly.  The original test logic has been superseded by the pytest suite.
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def main() -> int:
    """Run the e2e smoke suite via pytest and forward the exit code."""
    cmd = [
        sys.executable, "-m", "pytest",
        "brokers/dhan/tests/regression/test_e2e_smoke.py",
        "-v", "--tb=short",
    ]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())


# ---------------------------------------------------------------------------
# Legacy function retained so that anything importing this module still works.
# ---------------------------------------------------------------------------

def test_all_modes_options_futures_depth():
    """Legacy entry point — now delegates to pytest."""
    sys.exit(main())


def _legacy_placeholder():
    """The original imperative test code has been migrated to the pytest suite.

    See: brokers/dhan/tests/regression/test_e2e_smoke.py

    The tests below are kept as dead code for reference only; they are NOT
    executed by this script any longer.
    """

    console.print("\n[bold cyan]═" * 70)
    console.print("[bold]🔵 DHAN BROKER — ALL MODES, OPTIONS, FUTURES, DEPTH TEST[/bold]")
    console.print("[bold cyan]═" * 70)

    try:
        from infrastructure.config.env_loader import load_env_file
        from cli.services.broker_registry import bootstrap_gateway

        # Load .env.local
        env_path = PROJECT_ROOT / ".env.local"
        if not env_path.exists():
            console.print("[red]✗ .env.local not found[/red]")
            return False

        load_env_file(env_path)
        console.print("[dim]✓ Loaded .env.local[/dim]")

        # Create gateway
        console.print("\n[cyan]Creating Dhan gateway...[/cyan]")
        t0 = time.time()
        bootstrap = bootstrap_gateway(
            "dhan",
            env_path=env_path,
            load_instruments=True,
            require_authenticated=True,
        )
        latency = (time.time() - t0) * 1000

        if not bootstrap.live_ready or bootstrap.gateway is None:
            console.print(
                f"[red]✗ Dhan bootstrap failed: status={bootstrap.status.value} "
                f"error={bootstrap.error}[/red]"
            )
            return False

        gateway = bootstrap.gateway
        console.print(f"[green]✓ Dhan gateway ready ({latency:.0f}ms)[/green]")

        conn = gateway._conn

        # ============================================================
        # TEST 1: All Streaming Modes (LTP, QUOTE, FULL)
        # ============================================================
        console.print("\n" + "[bold]═" * 70)
        console.print("[bold]TEST 1: Streaming Modes (LTP, QUOTE, FULL)[/bold]")
        console.print("[bold]═" * 70)

        symbols_to_test = [
            ("RELIANCE", "NSE"),
            ("TCS", "NSE"),
            ("INFOSYS", "NSE"),
        ]

        for symbol, exchange in symbols_to_test:
            console.print(f"\n[cyan]Testing {symbol} ({exchange})...[/cyan]")

            # Mode 1: LTP
            console.print(f"  [yellow]Mode LTP[/yellow]")
            try:
                t0 = time.time()
                ltp = gateway.ltp(symbol, exchange)
                latency = (time.time() - t0) * 1000
                console.print(f"  [green]✓ LTP: ₹{ltp} ({latency:.0f}ms)[/green]")
            except Exception as e:
                console.print(f"  [red]✗ LTP failed: {e}[/red]")

            time.sleep(0.15)

            # Mode 2: QUOTE
            console.print(f"  [yellow]Mode QUOTE[/yellow]")
            try:
                t0 = time.time()
                quote = gateway.quote(symbol, exchange)
                latency = (time.time() - t0) * 1000
                console.print(
                    f"  [green]✓ Quote: LTP=₹{quote.ltp}, "
                    f"Volume={quote.volume:,}, "
                    f"Open=₹{quote.open}, High=₹{quote.high}, "
                    f"Low=₹{quote.low} ({latency:.0f}ms)[/green]"
                )
            except Exception as e:
                console.print(f"  [red]✗ Quote failed: {e}[/red]")

            time.sleep(0.15)

            # Mode 3: FULL (via streaming subscription)
            console.print(f"  [yellow]Mode FULL (streaming)[/yellow]")
            try:
                ticks = []
                tick_lock = threading.Lock()

                def on_tick(data):
                    with tick_lock:
                        ticks.append(data)

                # Subscribe to FULL mode
                feed = gateway.stream(symbol, exchange, mode="FULL", on_tick=on_tick)
                console.print(f"  [dim]Subscribed to FULL mode, waiting 5s for ticks...[/dim]")

                # Wait for ticks
                time.sleep(5)

                with tick_lock:
                    tick_count = len(ticks)

                if tick_count > 0:
                    sample = ticks[0]
                    ltp_val = sample.get("ltp", "?") if isinstance(sample, dict) else getattr(sample, "ltp", "?")
                    console.print(f"  [green]✓ FULL mode: {tick_count} ticks received, LTP={ltp_val}[/green]")
                else:
                    console.print(f"  [yellow]⚠ FULL mode: 0 ticks in 5s (market may be closed)[/yellow]")

            except Exception as e:
                console.print(f"  [red]✗ FULL mode failed: {e}[/red]")

            time.sleep(0.3)

        # ============================================================
        # TEST 2: Options Chain
        # ============================================================
        console.print("\n" + "[bold]═" * 70)
        console.print("[bold]TEST 2: Options Chain (NIFTY, BANKNIFTY)[/bold]")
        console.print("[bold]═" * 70)

        for underlying in ["NIFTY", "BANKNIFTY"]:
            exchange = "NFO"
            console.print(f"\n[cyan]Testing {underlying} Options...[/cyan]")

            try:
                # Get option chain
                t0 = time.time()
                chain = gateway.option_chain(underlying, exchange)
                latency = (time.time() - t0) * 1000

                console.print(f"  [green]✓ Options chain retrieved ({latency:.0f}ms)[/green]")

                # Check strikes
                if hasattr(chain, 'strikes'):
                    console.print(f"  [green]  - Strikes: {len(chain.strikes)}[/green]")

                # Check if it has expiries
                if hasattr(chain, 'expiries'):
                    console.print(f"  [green]  - Expiries: {len(chain.expiries)}[/green]")
                    if chain.expiries:
                        console.print(f"  [dim]    Nearest: {chain.expiries[0]}[/dim]")
                        console.print(f"  [dim]    Farthest: {chain.expiries[-1]}[/dim]")

                # Test extended capabilities for expiries
                try:
                    ext = gateway.extended
                    expiries = ext.get_option_expiries(underlying, exchange)
                    if expiries:
                        console.print(f"  [green]  - Extended API: {len(expiries)} expiries available[/green]")
                except Exception as e:
                    console.print(f"  [yellow]  ⚠ Extended expiries failed: {e}[/yellow]")

            except Exception as e:
                console.print(f"  [red]✗ Options chain failed: {e}[/red]")

            time.sleep(0.3)

        # ============================================================
        # TEST 3: Futures Chain
        # ============================================================
        console.print("\n" + "[bold]═" * 70)
        console.print("[bold]TEST 3: Futures Chain (NIFTY, RELIANCE)[/bold]")
        console.print("[bold]═" * 70)

        for underlying in ["NIFTY", "RELIANCE"]:
            exchange = "NFO"
            console.print(f"\n[cyan]Testing {underlying} Futures...[/cyan]")

            try:
                # Get futures chain
                t0 = time.time()
                futures = gateway.future_chain(underlying, exchange)
                latency = (time.time() - t0) * 1000

                console.print(f"  [green]✓ Futures chain retrieved ({latency:.0f}ms)[/green]")

                # Check contracts
                if hasattr(futures, 'contracts'):
                    console.print(f"  [green]  - Contracts: {len(futures.contracts)}[/green]")
                    if futures.contracts:
                        first = futures.contracts[0]
                        console.print(f"  [dim]    First: {first.symbol if hasattr(first, 'symbol') else 'N/A'} "
                                    f"(expiry: {first.expiry if hasattr(first, 'expiry') else 'N/A'})[/dim]")

            except Exception as e:
                console.print(f"  [red]✗ Futures chain failed: {e}[/red]")

            time.sleep(0.3)

        # ============================================================
        # TEST 4: Market Depth (REST + WebSocket Depth-20)
        # ============================================================
        console.print("\n" + "[bold]═" * 70)
        console.print("[bold]TEST 4: Market Depth (NSE - TCS, RELIANCE)[/bold]")
        console.print("[bold]═" * 70)

        for symbol, exchange in [("TCS", "NSE"), ("RELIANCE", "NSE")]:
            console.print(f"\n[cyan]Testing {symbol} ({exchange}) Depth...[/cyan]")

            # Test 4a: REST Depth (5-level)
            console.print(f"  [yellow]REST Depth (5-level)[/yellow]")
            try:
                t0 = time.time()
                depth = gateway.depth(symbol, exchange)
                latency = (time.time() - t0) * 1000

                console.print(
                    f"  [green]✓ REST Depth: {len(depth.bids)} bids, "
                    f"{len(depth.asks)} asks ({latency:.0f}ms)[/green]"
                )

                if depth.bids:
                    console.print(f"  [dim]    Top Bid: ₹{depth.bids[0].price}, "
                                f"Qty: {depth.bids[0].quantity}[/dim]")
                if depth.asks:
                    console.print(f"  [dim]    Top Ask: ₹{depth.asks[0].price}, "
                                f"Qty: {depth.asks[0].quantity}[/dim]")

            except Exception as e:
                console.print(f"  [red]✗ REST Depth failed: {e}[/red]")

            time.sleep(0.2)

            # Test 4b: WebSocket Depth-20
            console.print(f"  [yellow]WebSocket Depth-20[/yellow]")
            try:
                depth_updates = []
                depth_lock = threading.Lock()

                def on_depth(data):
                    with depth_lock:
                        depth_updates.append(data)

                # Subscribe to depth-20
                t0 = time.time()
                depth_20 = gateway.depth_20(symbol, exchange, on_depth=on_depth)
                initial_latency = (time.time() - t0) * 1000

                console.print(
                    f"  [green]✓ Depth-20 subscribed: {len(depth_20.bids)} bids, "
                    f"{len(depth_20.asks)} asks (initial, {initial_latency:.0f}ms)[/green]"
                )

                # Wait for WebSocket updates
                console.print(f"  [dim]Waiting 5s for depth updates...[/dim]")
                time.sleep(5)

                with depth_lock:
                    update_count = len(depth_updates)

                if update_count > 0:
                    last_depth = depth_updates[-1]
                    console.print(
                        f"  [green]✓ Depth-20 live: {update_count} updates received, "
                        f"last: {len(last_depth.bids)} bids, {len(last_depth.asks)} asks[/green]"
                    )
                else:
                    console.print(f"  [yellow]⚠ Depth-20: 0 WebSocket updates in 5s "
                                f"(using REST fallback)[/yellow]")

            except Exception as e:
                console.print(f"  [red]✗ Depth-20 failed: {e}[/red]")
                import traceback
                traceback.print_exc()

            time.sleep(0.3)

        # ============================================================
        # SUMMARY
        # ============================================================
        console.print("\n" + "[bold cyan]═" * 70)
        console.print("[bold]✓ ALL TESTS COMPLETE[/bold]")
        console.print("[bold cyan]═" * 70)

        console.print("\n[bold]Summary:[/bold]")
        console.print("  ✓ Streaming modes: LTP, QUOTE, FULL")
        console.print("  ✓ Options chain: NIFTY, BANKNIFTY")
        console.print("  ✓ Futures chain: NIFTY, RELIANCE")
        console.print("  ✓ Market depth: REST (5-level) + WebSocket (20-level)")
        console.print("\n[dim]All tests executed with real Dhan LIVE credentials[/dim]")

        # Close gateway
        gateway.close()
        console.print("[dim]✓ Gateway closed[/dim]")

        return True

    except Exception as e:
        console.print(f"\n[red]✗ Test failed: {e}[/red]")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_all_modes_options_futures_depth()
    sys.exit(0 if success else 1)
