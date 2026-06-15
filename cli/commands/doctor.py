"""CLI command handler for the doctor connectivity checks."""

from __future__ import annotations

from datetime import date, timedelta

from rich.console import Console
from rich.table import Table

from cli.services.broker_service import BrokerService


def run_doctor(broker_service: BrokerService, console: Console) -> None:
    """Execute all connection and diagnostics checks using the new BrokerGateway."""
    console.print(
        f"Running connectivity diagnostics on active broker: "
        f"[bold yellow]{broker_service.active_broker_name.upper()}[/bold yellow]"
    )
    console.print()

    gw = broker_service.active_broker
    results: list[tuple[str, str, str]] = []

    # 1. Instrument Catalog Check
    try:
        resolver = gw.instruments
        stats = resolver.stats()
        if stats.get("loaded") and stats.get("total", 0) > 0:
            results.append((
                "Instrument Catalog",
                "PASS",
                f"Loaded {stats['total']:,} instruments into the symbol resolver.",
            ))
        else:
            results.append((
                "Instrument Catalog",
                "FAIL",
                "Instrument catalog is not loaded or empty.",
            ))
    except Exception as e:
        results.append((
            "Instrument Catalog",
            "FAIL",
            f"Instrument catalog check failed: {e}",
        ))

    # 2. Quote Check
    try:
        symbol = "RELIANCE"
        exchange = "NSE"
        quote = gw.market_data.get_quote(symbol, exchange)
        if quote is not None:
            results.append((
                "Quote Check",
                "PASS",
                f"Retrieved live quote for {symbol}: LTP={quote.ltp:.2f}",
            ))
        else:
            results.append((
                "Quote Check",
                "FAIL",
                f"Quote endpoint returned None for symbol {symbol}.",
            ))
    except Exception as e:
        results.append((
            "Quote Check",
            "FAIL",
            f"Quote API verification failed: {e}",
        ))

    # 3. Market Depth Check
    import time as _time
    _time.sleep(2)
    try:
        symbol = "RELIANCE"
        exchange = "NSE"
        depth = gw.market_data.get_depth(symbol, exchange)
        if depth is not None and (depth.bids or depth.asks):
            results.append((
                "Market Depth Check",
                "PASS",
                f"Retrieved L2 depth for {symbol}: {len(depth.bids)} bids, {len(depth.asks)} asks.",
            ))
        else:
            results.append((
                "Market Depth Check",
                "FAIL",
                "Market depth endpoint returned empty data.",
            ))
    except Exception as e:
        results.append((
            "Market Depth Check",
            "FAIL",
            f"Market depth verification failed: {e}",
        ))

    # 4. Historical Data Check
    try:
        symbol = "RELIANCE"
        exchange = "NSE"
        to_dt = date.today().isoformat()
        from_dt = (date.today() - timedelta(days=5)).isoformat()
        hist_df = gw.historical.get_historical(symbol, exchange, from_dt, to_dt, timeframe="1D")
        if hist_df is not None and not hist_df.empty:
            results.append((
                "Historical Data Check",
                "PASS",
                f"Fetched {len(hist_df)} historical candles successfully.",
            ))
        else:
            results.append((
                "Historical Data Check",
                "FAIL",
                "Historical data endpoint returned empty DataFrame.",
            ))
    except Exception as e:
        results.append((
            "Historical Data Check",
            "FAIL",
            f"Historical data verification failed: {e}",
        ))

    # 5. Order API Check
    try:
        orders = gw.orders.get_orderbook()
        results.append((
            "Order API Check",
            "PASS",
            f"Retrieved {len(orders)} orders for today. Endpoints are active and readable.",
        ))
    except Exception as e:
        results.append((
            "Order API Check",
            "FAIL",
            f"Order API retrieval failed: {e}",
        ))

    # 6. Position Sync Check
    try:
        positions = gw.portfolio.get_positions()
        holdings = gw.portfolio.get_holdings()
        results.append((
            "Position Sync Check",
            "PASS",
            f"Positions synced ({len(positions)} open). Holdings synced ({len(holdings)} assets).",
        ))
    except Exception as e:
        results.append((
            "Position Sync Check",
            "FAIL",
            f"Portfolio sync check failed: {e}",
        ))

    # 7. Balance Check
    try:
        balance = gw.portfolio.get_balance()
        results.append((
            "Balance Check",
            "PASS",
            f"Available: Rs. {balance.available_balance:,.2f} | SOD Limit: Rs. {balance.sod_limit:,.2f}.",
        ))
    except Exception as e:
        results.append((
            "Balance Check",
            "FAIL",
            f"Balance retrieval failed: {e}",
        ))

    # 8. LifecycleManager Health (B8+B9 followup)
    # Every ManagedService in the system is owned by the broker's
    # LifecycleManager. The doctor reports the state of each
    # registered service so operators can spot FAILED/STOPPED
    # services before they cause a production incident.
    try:
        snapshot = broker_service.lifecycle.health_snapshot()
        if not snapshot:
            results.append((
                "Lifecycle Health",
                "WARN",
                "No ManagedServices registered (lifecycle empty).",
            ))
        else:
            failed = [
                (n, info.get("state", "UNKNOWN"))
                for n, info in snapshot.items()
                if info.get("state") in ("FAILED", "UNHEALTHY", "STOPPED")
                and n != "http.observability"  # http.observability is ok if STOPPED before init
            ]
            if failed:
                results.append((
                    "Lifecycle Health",
                    "FAIL",
                    f"{len(failed)} service(s) not healthy: {', '.join(n for n, _ in failed[:3])}",
                ))
            else:
                results.append((
                    "Lifecycle Health",
                    "PASS",
                    f"{len(snapshot)} ManagedService(s) healthy: {', '.join(snapshot.keys())}",
                ))
    except Exception as e:
        results.append((
            "Lifecycle Health",
            "FAIL",
            f"Lifecycle health snapshot failed: {e}",
        ))

    # 9. OMS RiskManager State (B7 + A2+A3 + C.1)
    # The OMS's RiskManager is the canonical risk gate on the live
    # path. The doctor reports the kill-switch state, the daily PnL
    # (so the operator can see if a loss-limit is approaching), and
    # the last-reset time (so the operator can see if the IST 00:00
    # rollover fired).
    try:
        if broker_service.trading_context is not None:
            rm = broker_service.trading_context.risk_manager
            snap = rm.snapshot()
            ks = "ACTIVE" if snap.get("kill_switch") else "inactive"
            daily_pnl = float(snap.get("daily_pnl", 0))
            resets = int(snap.get("reset_count", 0))
            results.append((
                "OMS RiskManager",
                "PASS",
                f"kill_switch={ks} | daily_pnl={daily_pnl:.2f} | resets={resets}",
            ))
        else:
            results.append((
                "OMS RiskManager",
                "WARN",
                "No TradingContext (gateway init failed or mock mode).",
            ))
    except Exception as e:
        results.append((
            "OMS RiskManager",
            "FAIL",
            f"OMS risk snapshot failed: {e}",
        ))

    # 10. HTTP Observability Surface (B8+B9)
    # The /healthz, /readyz, /metrics endpoints on port 8765 are
    # the operator's primary observability surface. The doctor
    # checks the server is running and reports the bound port.
    try:
        server = broker_service.http_observability
        if server is not None:
            h = server.health()
            port = h.metrics.get("port", 0)
            results.append((
                "HTTP Observability",
                "PASS" if h.state.value == "HEALTHY" else "WARN",
                f"listening on 127.0.0.1:{port} (state={h.state.value})",
            ))
        else:
            results.append((
                "HTTP Observability",
                "WARN",
                "Server not started (bind may have failed or init incomplete).",
            ))
    except Exception as e:
        results.append((
            "HTTP Observability",
            "FAIL",
            f"HTTP observability check failed: {e}",
        ))

    # Render results table
    table = Table(title="System Doctor Diagnostics Report", header_style="bold yellow")
    table.add_column("Diagnostics Check Item", style="bold white")
    table.add_column("Status", justify="center")
    table.add_column("Detailed Observation & Result Info", style="dim white")

    for name, status, details in results:
        if status == "PASS":
            status_str = "[green]PASS[/green]"
        elif status == "WARNING":
            status_str = "[yellow]WARN[/yellow]"
        else:
            status_str = "[red]FAIL[/red]"

        table.add_row(name, status_str, details)

    console.print(table)


def run(args: list[str], broker_service: BrokerService, console: Console) -> None:
    """Entry point for doctor subcommand."""
    run_doctor(broker_service, console)
