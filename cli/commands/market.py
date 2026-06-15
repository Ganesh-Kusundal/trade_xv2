"""CLI command handler for market data operations."""

from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta

from rich.console import Console
from rich.live import Live
from rich.table import Table

from cli.services.broker_service import BrokerService

# Indices whose underlying segment uses INDEX exchange
_INDEX_UNDERLYINGS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "NIFTYNXT50"}


def resolve_exchange(symbol: str) -> str:
    """Resolve the exchange for a given symbol."""
    sym = symbol.upper().strip()
    if sym in _INDEX_UNDERLYINGS:
        return "INDEX"
    # Options have strike digits followed by CE or PE at the end. Futures contain FUT.
    if re.search(r"\d+(CE|PE)$", sym) or "FUT" in sym:
        return "NFO"
    return "NSE"


def show_quote(
    broker_service: BrokerService, symbol: str, console: Console, live_mode: bool = False
) -> None:
    """Display real-time quote for a symbol."""
    gw = broker_service.active_broker
    exchange = resolve_exchange(symbol)

    def generate_table() -> Table:
        quote = gw.market_data.get_quote(symbol, exchange)
        table = Table(
            title=f"Quote Terminal: {symbol.upper()} ({exchange})", header_style="bold green"
        )
        table.add_column("Metric", style="bold white")
        table.add_column("Value", justify="right")

        if quote is not None:
            ts_str = (
                quote.timestamp.strftime("%H:%M:%S")
                if isinstance(quote.timestamp, datetime)
                else str(quote.timestamp)
            )
            table.add_row("Last Traded Price (LTP)", f"Rs. {quote.ltp:,.2f}")
            table.add_row("Open", f"Rs. {quote.open:,.2f}")
            table.add_row("High", f"Rs. {quote.high:,.2f}")
            table.add_row("Low", f"Rs. {quote.low:,.2f}")
            table.add_row("Prev Close", f"Rs. {quote.close:,.2f}")
            table.add_row("Change", f"Rs. {quote.change:,.2f}")
            table.add_row("Volume", f"{quote.volume:,}")
            table.add_row("Last Updated", ts_str)
        else:
            table.add_row("Status", "[red]No quote data received[/red]")
        return table

    if not live_mode:
        console.print(generate_table())
    else:
        console.print("[yellow]Starting Quote Terminal. Press Ctrl+C to exit...[/yellow]")
        with Live(generate_table(), console=console, refresh_per_second=1) as live:
            try:
                while True:
                    time.sleep(1)
                    live.update(generate_table())
            except KeyboardInterrupt:
                console.print("\n[yellow]Quote Terminal closed.[/yellow]")


def show_depth(
    broker_service: BrokerService, symbol: str, console: Console, live_mode: bool = False
) -> None:
    """Display L2 market depth (bids/asks)."""
    gw = broker_service.active_broker
    exchange = resolve_exchange(symbol)

    def generate_table() -> Table:
        depth = gw.market_data.get_depth(symbol, exchange)
        table = Table(title=f"Market Depth L2: {symbol.upper()}", header_style="bold magenta")
        table.add_column("Bid Qty", style="green", justify="right")
        table.add_column("Bid Price", style="bold green", justify="right")
        table.add_column("Ask Price", style="bold red", justify="right")
        table.add_column("Ask Qty", style="red", justify="right")

        if depth is not None and (depth.bids or depth.asks):
            # Show up to 5 levels for CLI readability
            max_levels = max(len(depth.bids), len(depth.asks))
            for i in range(min(max_levels, 5)):
                bid = depth.bids[i] if i < len(depth.bids) else None
                ask = depth.asks[i] if i < len(depth.asks) else None
                table.add_row(
                    f"{bid.quantity:,}" if bid else "-",
                    f"{bid.price:,.2f}" if bid else "-",
                    f"{ask.price:,.2f}" if ask else "-",
                    f"{ask.quantity:,}" if ask else "-",
                )
        else:
            table.add_row("-", "No depth data", "No depth data", "-")
        return table

    if not live_mode:
        console.print(generate_table())
    else:
        console.print("[yellow]Starting Depth Terminal. Press Ctrl+C to exit...[/yellow]")
        with Live(generate_table(), console=console, refresh_per_second=1) as live:
            try:
                while True:
                    time.sleep(1)
                    live.update(generate_table())
            except KeyboardInterrupt:
                console.print("\n[yellow]Depth Terminal closed.[/yellow]")


def show_option_chain(
    broker_service: BrokerService,
    symbol: str,
    console: Console,
    expiry: str | None = None,
) -> None:
    """Display option chain for an underlying asset."""
    gw = broker_service.active_broker
    sym = symbol.upper().strip()
    exchange = "INDEX" if sym in _INDEX_UNDERLYINGS else "NFO"

    # Auto-resolve expiry if not provided
    if not expiry:
        try:
            raw_expiries = gw.options.get_expiries(sym, exchange)
            today_str = date.today().isoformat()
            future_expiries = sorted([e for e in raw_expiries if e >= today_str])
            expiry = future_expiries[0] if future_expiries else None
        except Exception:
            pass

    if not expiry:
        # Hard fallback: next Thursday
        today = date.today()
        days_to_thu = (3 - today.weekday()) % 7 or 7
        expiry = (date.today() + timedelta(days=days_to_thu)).isoformat()

    console.print(
        f"[dim]Fetching option chain for [bold]{sym}[/bold] | Expiry: [bold cyan]{expiry}[/bold cyan]...[/dim]"
    )

    try:
        chain = gw.options.get_option_chain(sym, exchange, expiry)

        table = Table(
            title=f"Option Chain -- {sym}  |  Expiry: {expiry}",
            header_style="bold cyan",
            show_lines=True,
            border_style="dim blue",
        )
        # CE side
        table.add_column("CE OI", style="cyan", justify="right")
        table.add_column("CE Vol", justify="right")
        table.add_column("CE IV%", style="dim cyan", justify="right")
        table.add_column("CE LTP", style="bold green", justify="right")
        table.add_column("CE Delta", style="green", justify="right")
        table.add_column("CE Theta", style="green", justify="right")
        # Strike
        table.add_column("Strike", style="bold yellow", justify="center", min_width=10)
        # PE side
        table.add_column("PE Theta", style="red", justify="right")
        table.add_column("PE Delta", style="red", justify="right")
        table.add_column("PE LTP", style="bold red", justify="right")
        table.add_column("PE IV%", style="dim red", justify="right")
        table.add_column("PE Vol", justify="right")
        table.add_column("PE OI", style="cyan", justify="right")

        strikes = chain.get("strikes", [])
        spot = chain.get("spot", 0)

        if strikes:
            all_strike_vals = [s["strike"] for s in strikes]

            # Show 14 strikes centred on ATM (7 ITM + 7 OTM)
            idx = len(all_strike_vals) // 2
            visible_strikes = strikes[max(0, idx - 7) : min(len(strikes), idx + 7)]

            console.print(
                f"  [dim]Spot: [bold]{spot:,.2f}[/bold] | Total strikes: [bold]{len(all_strike_vals)}[/bold] | Showing {len(visible_strikes)} centred on ATM[/dim]\n"
            )

            def _fmt_dec(val):
                if val is None:
                    return "[dim]-[/dim]"
                try:
                    return f"{float(val):,.2f}"
                except (ValueError, TypeError):
                    return "[dim]-[/dim]"

            def _fmt_int(val):
                if val is None:
                    return "[dim]-[/dim]"
                try:
                    return f"{int(val):,}"
                except (ValueError, TypeError):
                    return "[dim]-[/dim]"

            def _fmt_iv(val):
                if val is None:
                    return "[dim]-[/dim]"
                try:
                    return f"{float(val):.1f}%"
                except (ValueError, TypeError):
                    return "[dim]-[/dim]"

            for entry in visible_strikes:
                strike_val = entry["strike"]
                ce = entry.get("call", {}) or {}
                pe = entry.get("put", {}) or {}

                # Determine ATM highlight
                atm_dist = min(
                    (abs(float(s["strike"]) - float(spot)) for s in strikes), default=0
                )
                is_atm = abs(float(strike_val) - float(spot)) == atm_dist
                strike_label = (
                    f"[bold yellow on blue] {float(strike_val):>10,.0f} [/bold yellow on blue]"
                    if is_atm
                    else f"{float(strike_val):,.0f}"
                )

                table.add_row(
                    _fmt_int(ce.get("oi")),
                    _fmt_int(ce.get("volume")),
                    _fmt_iv(ce.get("iv")),
                    _fmt_dec(ce.get("ltp")),
                    _fmt_dec(ce.get("delta")),
                    _fmt_dec(ce.get("theta")),
                    strike_label,
                    _fmt_dec(pe.get("theta")),
                    _fmt_dec(pe.get("delta")),
                    _fmt_dec(pe.get("ltp")),
                    _fmt_iv(pe.get("iv")),
                    _fmt_int(pe.get("volume")),
                    _fmt_int(pe.get("oi")),
                )
        else:
            table.add_row(
                "-", "-", "-", "-", "-", "-", "No Chain Data", "-", "-", "-", "-", "-", "-"
            )

        console.print(table)
    except Exception as exc:
        import traceback

        console.print(f"[red bold]Error fetching option chain:[/red bold] {exc}")
        console.print(f"[dim]{traceback.format_exc()}[/dim]")


def show_futures(
    broker_service: BrokerService, symbol: str, console: Console
) -> None:
    """Display futures contract details."""
    gw = broker_service.active_broker
    sym = symbol.upper().strip()
    exchange = "NFO"
    # Commodities route to MCX
    if any(c in sym for c in ("GOLD", "SILVER", "CRUDE", "NATURAL", "COPPER", "ZINC")):
        exchange = "MCX"

    try:
        contracts = gw.futures.get_contracts(sym, exchange)

        table = Table(title=f"Futures Contracts for {sym}", header_style="bold yellow")
        table.add_column("Expiry", style="bold white")
        table.add_column("Trading Symbol", style="white")
        table.add_column("Security ID", justify="center")
        table.add_column("Lot Size", justify="right")

        if contracts:
            for c in contracts:
                table.add_row(
                    c.get("expiry") or "N/A",
                    c.get("symbol") or "N/A",
                    str(c.get("security_id", "N/A")),
                    str(c.get("lot_size", "N/A")),
                )
        else:
            table.add_row("No contracts found", "-", "-", "-")

        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error fetching futures details: {exc}[/red]")


def show_historical(
    broker_service: BrokerService, symbol: str, console: Console
) -> None:
    """Display historical candles summary and preview."""
    gw = broker_service.active_broker
    exchange = resolve_exchange(symbol)
    to_date = date.today().isoformat()
    from_date = (date.today() - timedelta(days=10)).isoformat()

    try:
        df = gw.historical.get_historical(symbol, exchange, from_date, to_date, timeframe="1D")

        table = Table(
            title=f"Historical Data Preview: {symbol.upper()}", header_style="bold magenta"
        )
        table.add_column("Timestamp", style="bold white")
        table.add_column("Open", justify="right")
        table.add_column("High", justify="right")
        table.add_column("Low", justify="right")
        table.add_column("Close", justify="right")
        table.add_column("Volume", justify="right")

        if df is not None and not df.empty:
            for _, row in df.tail(5).iterrows():
                ts_val = row.get("timestamp")
                ts_str = (
                    ts_val.strftime("%Y-%m-%d")
                    if isinstance(ts_val, datetime)
                    else str(ts_val) if ts_val is not None else "N/A"
                )
                table.add_row(
                    ts_str,
                    f"{row['open']:,.2f}",
                    f"{row['high']:,.2f}",
                    f"{row['low']:,.2f}",
                    f"{row['close']:,.2f}",
                    f"{int(row['volume']):,}",
                )
            console.print(table)
            console.print()
            first_ts = df["timestamp"].iloc[0]
            last_ts = df["timestamp"].iloc[-1]
            first_str = first_ts.strftime("%Y-%m-%d") if isinstance(first_ts, datetime) else str(first_ts)
            last_str = last_ts.strftime("%Y-%m-%d") if isinstance(last_ts, datetime) else str(last_ts)
            console.print(
                f"Total Rows: [bold cyan]{len(df)}[/bold cyan] candles | First: {first_str} | Last: {last_str}"
            )
        else:
            table.add_row("No historical data found", "-", "-", "-", "-", "-")
            console.print(table)
    except Exception as exc:
        console.print(f"[red]Error fetching historical data: {exc}[/red]")


def show_stream(
    broker_service: BrokerService, symbol: str, console: Console
) -> None:
    """Display real-time streaming ticks in a rolling table."""
    gw = broker_service.active_broker
    exchange = resolve_exchange(symbol)
    console.print(
        f"[yellow]Starting Live Stream Monitor for {symbol} ({exchange}). Press Ctrl+C to exit...[/yellow]"
    )

    rows: list[list[str]] = []

    table = Table(header_style="bold cyan")
    table.add_column("Timestamp", style="dim white")
    table.add_column("Price", style="bold green", justify="right")
    table.add_column("Open", justify="right")
    table.add_column("High", justify="right")
    table.add_column("Low", justify="right")
    table.add_column("Volume", justify="right")

    with Live(table, console=console, refresh_per_second=2) as live:
        try:
            for _ in range(20):  # Simulate 20 ticks
                quote = gw.market_data.get_quote(symbol, exchange)
                if quote is not None:
                    ts_str = (
                        quote.timestamp.strftime("%H:%M:%S.%f")[:-3]
                        if isinstance(quote.timestamp, datetime)
                        else str(quote.timestamp)
                    )

                    rows.append(
                        [
                            ts_str,
                            f"Rs. {quote.ltp:,.2f}",
                            f"{quote.open:,.2f}",
                            f"{quote.high:,.2f}",
                            f"{quote.low:,.2f}",
                            f"{quote.volume:,}",
                        ]
                    )
                    # Keep last 10 ticks
                    if len(rows) > 10:
                        rows.pop(0)

                    # Rebuild table
                    new_table = Table(
                        title=f"Live Tick Stream: {symbol}", header_style="bold cyan"
                    )
                    new_table.add_column("Timestamp", style="dim white")
                    new_table.add_column("Price", style="bold green", justify="right")
                    new_table.add_column("Open", justify="right")
                    new_table.add_column("High", justify="right")
                    new_table.add_column("Low", justify="right")
                    new_table.add_column("Volume", justify="right")

                    for r in rows:
                        new_table.add_row(*r)

                    live.update(new_table)
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass

    console.print("[yellow]Tick Stream Monitor stopped.[/yellow]")


def run(args: list[str], broker_service: BrokerService, console: Console) -> None:
    """Entry point for market data operations."""
    if not args:
        console.print(
            "[yellow]Usage: tradex quote|depth|option-chain|futures|historical|stream <symbol>[/yellow]"
        )
        return

    sub = args[0]
    sym = args[1] if len(args) > 1 else sub

    if sub == "quote":
        live_mode = "--live" in args[2:]
        show_quote(broker_service, sym, console, live_mode=live_mode)
    elif sub == "depth":
        live_mode = "--live" in args[2:]
        show_depth(broker_service, sym, console, live_mode=live_mode)
    elif sub == "option-chain":
        expiry = None
        if "--expiry" in args:
            idx = args.index("--expiry")
            if idx + 1 < len(args):
                expiry = args[idx + 1]
        show_option_chain(broker_service, sym, console, expiry=expiry)
    elif sub == "futures":
        show_futures(broker_service, sym, console)
    elif sub == "historical":
        show_historical(broker_service, sym, console)
    elif sub == "stream":
        show_stream(broker_service, sym, console)
    else:
        console.print(f"[red]Unknown market subcommand: {sub}[/red]")
        console.print(
            "[yellow]Available: quote | depth | option-chain | futures | historical | stream[/yellow]"
        )
