"""CLI command handler for market data operations."""

from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta

from rich.console import Console
from rich.live import Live
from rich.table import Table

from brokers.common.core.broker import Broker

# Indices whose underlying segment on Dhan is IDX_I (not NFO)
_INDEX_UNDERLYINGS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "NIFTYNXT50"}


def resolve_exchange(symbol: str) -> str:
    """Resolve the exchange for a given symbol."""
    sym = symbol.upper().strip()
    if sym in _INDEX_UNDERLYINGS:
        return "IDX"
    # Options have strike digits followed by CE or PE at the end. Futures contain FUT.
    if re.search(r"\d+(CE|PE)$", sym) or "FUT" in sym:
        return "NFO"
    return "NSE"


def show_quote(broker: Broker, symbol: str, console: Console, live_mode: bool = False) -> None:
    """Display real-time quote for a symbol."""
    exchange = resolve_exchange(symbol)

    def generate_table() -> Table:
        df = broker.get_quote(symbol, exchange)
        table = Table(
            title=f"Quote Terminal: {symbol.upper()} ({exchange})", header_style="bold green"
        )
        table.add_column("Metric", style="bold white")
        table.add_column("Value", justify="right")

        if df is not None and not df.empty:
            row = df.iloc[0]
            ts_val = row["timestamp"]
            ts_str = ts_val.strftime("%H:%M:%S") if isinstance(ts_val, datetime) else str(ts_val)
            table.add_row("Last Traded Price (LTP)", f"Rs. {row['ltp']:,.2f}")
            table.add_row("Best Bid Price", f"Rs. {row['bid']:,.2f}")
            table.add_row("Best Ask Price", f"Rs. {row['ask']:,.2f}")
            table.add_row("Spread", f"Rs. {abs(row['ask'] - row['bid']):.2f}")
            table.add_row("Volume", f"{int(row['volume']):,}")
            table.add_row("Open Interest (OI)", f"{int(row['oi']):,}")
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


def show_depth(broker: Broker, symbol: str, console: Console, live_mode: bool = False) -> None:
    """Display L2 market depth (bids/asks)."""
    exchange = resolve_exchange(symbol)

    def generate_table() -> Table:
        df = broker.get_market_depth(symbol, exchange)
        table = Table(title=f"Market Depth L2: {symbol.upper()}", header_style="bold magenta")
        table.add_column("Bid Qty", style="green", justify="right")
        table.add_column("Bid Price", style="bold green", justify="right")
        table.add_column("Ask Price", style="bold red", justify="right")
        table.add_column("Ask Qty", style="red", justify="right")

        if df is not None and not df.empty:
            row = df.iloc[0]
            # Show up to 5 levels for CLI readability (broker supports 20)
            for i in range(1, 6):
                table.add_row(
                    f"{int(row.get(f'bid_qty_{i}', 0)):,}",
                    f"{row.get(f'bid_price_{i}', 0.0):,.2f}",
                    f"{row.get(f'ask_price_{i}', 0.0):,.2f}",
                    f"{int(row.get(f'ask_qty_{i}', 0)):,}",
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
    broker: Broker, symbol: str, console: Console, expiry: str | None = None
) -> None:
    """Display option chain for an underlying asset (Dhan v2 API)."""
    from datetime import date as _date

    sym = symbol.upper().strip()
    # Dhan v2: index underlyings use IDX_I segment, equity F&O uses NFO
    exchange = "IDX" if sym in _INDEX_UNDERLYINGS else "NFO"

    # Auto-resolve expiry from Dhan's expirylist API if not provided
    if not expiry:
        try:
            from brokers.common.core.instruments import InstrumentRegistry

            segment = InstrumentRegistry.exchange_segment(exchange)
            raw_expiries = broker.get_option_expiries_rest(sym, segment)
            today_str = _date.today().isoformat()
            future_expiries = sorted([e for e in raw_expiries if e >= today_str])
            expiry = future_expiries[0] if future_expiries else None
        except Exception:
            pass

    if not expiry:
        # Hard fallback: next Thursday
        today = _date.today()
        days_to_thu = (3 - today.weekday()) % 7 or 7
        expiry = (_date.today() + timedelta(days=days_to_thu)).isoformat()

    console.print(
        f"[dim]Fetching option chain for [bold]{sym}[/bold] | Expiry: [bold cyan]{expiry}[/bold cyan]…[/dim]"
    )

    try:
        df = broker.get_option_chain(symbol, exchange, expiry)

        table = Table(
            title=f"⛓  Option Chain — {sym}  |  Expiry: {expiry}",
            header_style="bold cyan",
            show_lines=True,
            border_style="dim blue",
        )
        # CE side
        table.add_column("CE OI", style="cyan", justify="right")
        table.add_column("CE Vol", justify="right")
        table.add_column("CE IV%", style="dim cyan", justify="right")
        table.add_column("CE LTP", style="bold green", justify="right")
        table.add_column("CE Bid", style="green", justify="right")
        table.add_column("CE Ask", style="green", justify="right")
        # Strike
        table.add_column("Strike ✦", style="bold yellow", justify="center", min_width=10)
        # PE side
        table.add_column("PE Bid", style="red", justify="right")
        table.add_column("PE Ask", style="red", justify="right")
        table.add_column("PE LTP", style="bold red", justify="right")
        table.add_column("PE IV%", style="dim red", justify="right")
        table.add_column("PE Vol", justify="right")
        table.add_column("PE OI", style="cyan", justify="right")

        if df is not None and not df.empty:
            ce_df = df[df["option_type"] == "CE"].set_index("strike")
            pe_df = df[df["option_type"] == "PE"].set_index("strike")

            median_strike = float(df["strike"].median())
            all_strikes = sorted(set(df["strike"]))
            # Show 14 strikes centred on ATM (7 ITM + 7 OTM)
            idx = len(all_strikes) // 2
            visible_strikes = all_strikes[max(0, idx - 7) : min(len(all_strikes), idx + 7)]

            console.print(
                f"  [dim]Total strikes available: [bold]{len(all_strikes)}[/bold] | Showing {len(visible_strikes)} centred on ATM ≈ {median_strike:,.0f}[/dim]\n"
            )

            for strike in visible_strikes:
                ce_row = ce_df.loc[strike] if strike in ce_df.index else None
                pe_row = pe_df.loc[strike] if strike in pe_df.index else None

                is_atm = abs(strike - median_strike) == min(
                    abs(s - median_strike) for s in all_strikes
                )
                strike_label = (
                    f"[bold yellow on blue] {strike:>10,.0f} [/bold yellow on blue]"
                    if is_atm
                    else f"{strike:,.0f}"
                )

                def _fmt_ltp(row):
                    if row is None:
                        return "[dim]-[/dim]"
                    v = row.get("ltp", float("nan")) if hasattr(row, "get") else row["ltp"]
                    return f"{float(v):,.2f}" if v == v else "[dim]-[/dim]"

                def _fmt_int(row, col):
                    if row is None:
                        return "[dim]-[/dim]"
                    v = row.get(col, None) if hasattr(row, "get") else row[col]
                    try:
                        return f"{int(v):,}"
                    except:
                        return "[dim]-[/dim]"

                def _fmt_iv(row):
                    if row is None:
                        return "[dim]-[/dim]"
                    v = row.get("iv", float("nan")) if hasattr(row, "get") else row["iv"]
                    try:
                        return f"{float(v):.1f}%"
                    except:
                        return "[dim]-[/dim]"

                def _fmt_price(row, col):
                    if row is None:
                        return "[dim]-[/dim]"
                    v = row.get(col, float("nan")) if hasattr(row, "get") else row[col]
                    try:
                        return f"{float(v):,.2f}"
                    except:
                        return "[dim]-[/dim]"

                table.add_row(
                    _fmt_int(ce_row, "oi"),
                    _fmt_int(ce_row, "volume"),
                    _fmt_iv(ce_row),
                    _fmt_ltp(ce_row),
                    _fmt_price(ce_row, "bid"),
                    _fmt_price(ce_row, "ask"),
                    strike_label,
                    _fmt_price(pe_row, "bid"),
                    _fmt_price(pe_row, "ask"),
                    _fmt_ltp(pe_row),
                    _fmt_iv(pe_row),
                    _fmt_int(pe_row, "volume"),
                    _fmt_int(pe_row, "oi"),
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


def show_futures(broker: Broker, symbol: str, console: Console) -> None:
    """Display futures contract details."""
    resolve_exchange(symbol)
    try:
        contracts = broker.instrument_service.get_futures(symbol)

        table = Table(title=f"Futures Contracts for {symbol.upper()}", header_style="bold yellow")
        table.add_column("Expiry", style="bold white")
        table.add_column("Trading Symbol", style="white")
        table.add_column("Security ID", justify="center")
        table.add_column("Lot Size", justify="right")

        if contracts:
            for c in contracts:
                table.add_row(
                    c.expiry or "N/A",
                    c.symbol,
                    c.security_id,
                    str(c.lot_size),
                )
        else:
            table.add_row("No contracts found", "-", "-", "-")

        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error fetching futures details: {exc}[/red]")


def show_historical(broker: Broker, symbol: str, console: Console) -> None:
    """Display historical candles summary and preview."""
    exchange = resolve_exchange(symbol)
    to_date = date.today()
    from_date = to_date - timedelta(days=10)

    try:
        df = broker.get_historical_data(symbol, exchange, from_date, to_date, timeframe="1d")

        table = Table(
            title=f"Historical Data Preview: {symbol.upper()}", header_style="bold magenta"
        )
        table.add_column("Timestamp", style="bold white")
        table.add_column("Open", justify="right")
        table.add_column("High", justify="right")
        table.add_column("Low", justify="right")
        table.add_column("Close", justify="right")
        table.add_column("Volume", justify="right")
        table.add_column("OI", justify="right")

        if df is not None and not df.empty:
            for _, row in df.tail(5).iterrows():
                ts_val = row["timestamp"]
                ts_str = (
                    ts_val.strftime("%Y-%m-%d") if isinstance(ts_val, datetime) else str(ts_val)
                )
                table.add_row(
                    ts_str,
                    f"{row['open']:,.2f}",
                    f"{row['high']:,.2f}",
                    f"{row['low']:,.2f}",
                    f"{row['close']:,.2f}",
                    f"{int(row['volume']):,}",
                    f"{int(row['oi']):,}",
                )
            console.print(table)
            console.print()
            console.print(
                f"Total Rows: [bold cyan]{len(df)}[/bold cyan] candles | First: {df['timestamp'].iloc[0].strftime('%Y-%m-%d')} | Last: {df['timestamp'].iloc[-1].strftime('%Y-%m-%d')}"
            )
        else:
            table.add_row("No historical data found", "-", "-", "-", "-", "-", "-")
            console.print(table)
    except Exception as exc:
        console.print(f"[red]Error fetching historical data: {exc}[/red]")


def show_stream(broker: Broker, symbol: str, console: Console) -> None:
    """Display real-time streaming ticks in a rolling table."""
    exchange = resolve_exchange(symbol)
    console.print(
        f"[yellow]Starting Live Stream Monitor for {symbol} ({exchange}). Press Ctrl+C to exit...[/yellow]"
    )

    table = Table(header_style="bold cyan")
    table.add_column("Timestamp", style="dim white")
    table.add_column("Price", style="bold green", justify="right")
    table.add_column("Bid", justify="right")
    table.add_column("Ask", justify="right")
    table.add_column("Volume", justify="right")

    rows: list[list[str]] = []

    with Live(table, console=console, refresh_per_second=2) as live:
        try:
            for _ in range(20):  # Simulate 20 ticks
                df = broker.get_quote(symbol, exchange)
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    ts_val = row["timestamp"]
                    ts_str = (
                        ts_val.strftime("%H:%M:%S.%f")[:-3]
                        if isinstance(ts_val, datetime)
                        else str(ts_val)
                    )

                    rows.append(
                        [
                            ts_str,
                            f"Rs. {row['ltp']:,.2f}",
                            f"{row['bid']:,.2f}",
                            f"{row['ask']:,.2f}",
                            f"{int(row['volume']):,}",
                        ]
                    )
                    # Keep last 10 ticks
                    if len(rows) > 10:
                        rows.pop(0)

                    # Rebuild table
                    new_table = Table(title=f"Live Tick Stream: {symbol}", header_style="bold cyan")
                    new_table.add_column("Timestamp", style="dim white")
                    new_table.add_column("Price", style="bold green", justify="right")
                    new_table.add_column("Bid", justify="right")
                    new_table.add_column("Ask", justify="right")
                    new_table.add_column("Volume", justify="right")

                    for r in rows:
                        new_table.add_row(*r)

                    live.update(new_table)
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass

    console.print("[yellow]Tick Stream Monitor stopped.[/yellow]")


def run(args: list[str], broker: Broker, console: Console) -> None:
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
        show_quote(broker, sym, console, live_mode=live_mode)
    elif sub == "depth":
        live_mode = "--live" in args[2:]
        show_depth(broker, sym, console, live_mode=live_mode)
    elif sub == "option-chain":
        expiry = None
        if "--expiry" in args:
            idx = args.index("--expiry")
            if idx + 1 < len(args):
                expiry = args[idx + 1]
        show_option_chain(broker, sym, console, expiry=expiry)
    elif sub == "futures":
        show_futures(broker, sym, console)
    elif sub == "historical":
        show_historical(broker, sym, console)
    elif sub == "stream":
        show_stream(broker, sym, console)
    else:
        console.print(f"[red]Unknown market subcommand: {sub}[/red]")
        console.print(
            "[yellow]Available: quote | depth | option-chain | futures | historical | stream[/yellow]"
        )
