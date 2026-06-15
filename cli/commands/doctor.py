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
