"""CLI command handler for market data operations.

All market data access goes through domain objects (Session → Universe → Instrument).
No broker gateway is referenced directly.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from rich.console import Console
from rich.live import Live
from rich.table import Table

from domain.symbols import normalize_symbol

if TYPE_CHECKING:
    from domain.universe import Session

logger = logging.getLogger(__name__)

# Indices whose underlying segment uses INDEX exchange — canonical set from indices module
from config.indices import INDEX_SYMBOLS as _INDEX_UNDERLYINGS

# ── Module-level Session (set once at startup) ───────────────────────
_session: Session | None = None


def set_session(session: Session) -> None:
    global _session
    _session = session


def get_session() -> Session:
    if _session is None:
        raise RuntimeError("Session not wired — call set_session() at startup")
    return _session


def resolve_exchange(symbol: str) -> str:
    """Resolve the exchange for a given symbol."""
    sym = normalize_symbol(symbol)
    if sym in _INDEX_UNDERLYINGS:
        return "INDEX"
    # Options have strike digits followed by CE or PE at the end. Futures contain FUT.
    if re.search(r"\d+(CE|PE)$", sym) or "FUT" in sym:
        return "NFO"
    return "NSE"


def _resolve_instrument(symbol: str):
    """Build a domain Instrument from a symbol string."""
    session = get_session()
    sym = normalize_symbol(symbol)
    exchange = resolve_exchange(sym)
    return session.universe.equity(sym, exchange), exchange


def show_quote(
    broker_service, symbol: str, console: Console, live_mode: bool = False
) -> None:
    """Display real-time quote for a symbol via domain objects."""
    instrument, exchange = _resolve_instrument(symbol)

    def generate_table() -> Table:
        q = instrument.refresh()
        table = Table(
            title=f"Quote Terminal: {normalize_symbol(symbol)} ({exchange})", header_style="bold green"
        )
        table.add_column("Metric", style="bold white")
        table.add_column("Value", justify="right")

        if q is not None:
            ts_str = (
                q.event_time.strftime("%H:%M:%S")
                if isinstance(q.event_time, datetime)
                else str(q.event_time)
            )
            table.add_row("Last Traded Price (LTP)", f"Rs. {q.ltp:,.2f}")
            table.add_row("Open", f"Rs. {q.open:,.2f}")
            table.add_row("High", f"Rs. {q.high:,.2f}")
            table.add_row("Low", f"Rs. {q.low:,.2f}")
            table.add_row("Prev Close", f"Rs. {q.close:,.2f}")
            table.add_row("Change", f"Rs. {q.change_pct:,.2f}")
            table.add_row("Volume", f"{q.volume:,}")
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
    broker_service, symbol: str, console: Console, live_mode: bool = False
) -> None:
    """Display L2 market depth (bids/asks) via domain objects."""
    instrument, exchange = _resolve_instrument(symbol)

    def generate_table() -> Table:
        depth = instrument.depth()
        table = Table(title=f"Market Depth L2: {normalize_symbol(symbol)}", header_style="bold magenta")
        table.add_column("Bid Qty", style="green", justify="right")
        table.add_column("Bid Price", style="bold green", justify="right")
        table.add_column("Ask Price", style="bold red", justify="right")
        table.add_column("Ask Qty", style="red", justify="right")

        if depth is not None and (depth.bids or depth.asks):
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


def _get_leg_greeks(leg, name: str):
    """Extract a greek value from an OptionLeg's greeks dict."""
    greeks = getattr(leg, "greeks", None)
    if greeks and isinstance(greeks, dict):
        return greeks.get(name)
    return None


def show_option_chain(
    broker_service,
    symbol: str,
    console: Console,
    expiry: str | None = None,
) -> None:
    """Display option chain for an underlying asset via domain objects."""
    session = get_session()
    sym = normalize_symbol(symbol)
    exchange = "INDEX" if sym in _INDEX_UNDERLYINGS else "NFO"
    instrument = session.universe.equity(sym, exchange)

    # Parse expiry to date for domain API
    expiry_date = None
    if expiry:
        try:
            expiry_date = date.fromisoformat(expiry)
        except ValueError:
            pass

    console.print(
        f"[dim]Fetching option chain for [bold]{sym}[/bold] | Expiry: [bold cyan]{expiry or 'auto'}[/bold cyan]...[/dim]"
    )

    try:
        chain = instrument.option_chain(expiry_date)

        table = Table(
            title=f"Option Chain -- {sym}  |  Expiry: {chain.expiry}",
            header_style="bold cyan",
            show_lines=True,
            border_style="dim blue",
        )
        table.add_column("CE OI", style="cyan", justify="right")
        table.add_column("CE Vol", justify="right")
        table.add_column("CE IV%", style="dim cyan", justify="right")
        table.add_column("CE LTP", style="bold green", justify="right")
        table.add_column("CE Delta", style="green", justify="right")
        table.add_column("CE Theta", style="green", justify="right")
        table.add_column("Strike", style="bold yellow", justify="center", min_width=10)
        table.add_column("PE Theta", style="red", justify="right")
        table.add_column("PE Delta", style="red", justify="right")
        table.add_column("PE LTP", style="bold red", justify="right")
        table.add_column("PE IV%", style="dim red", justify="right")
        table.add_column("PE Vol", justify="right")
        table.add_column("PE OI", style="cyan", justify="right")

        strikes = list(chain.strikes) if chain.strikes else []
        spot = chain.spot or 0

        if strikes:
            all_strike_vals = [float(s.strike) for s in strikes]
            idx = len(all_strike_vals) // 2
            visible_strikes = strikes[max(0, idx - 7) : min(len(strikes), idx + 7)]

            console.print(
                f"  [dim]Spot: [bold]{spot:,.2f}[/bold] | Total strikes: [bold]{len(all_strike_vals)}[/bold] | Showing {len(visible_strikes)} centred on ATM[/dim]\n"
            )

            for entry in visible_strikes:
                strike_val = float(entry.strike)
                ce = entry.call
                pe = entry.put

                atm_dist = min((abs(s - float(spot)) for s in all_strike_vals), default=0)
                is_atm = abs(strike_val - float(spot)) == atm_dist
                strike_label = (
                    f"[bold yellow on blue] {strike_val:>10,.0f} [/bold yellow on blue]"
                    if is_atm
                    else f"{strike_val:,.0f}"
                )

                table.add_row(
                    _fmt_int(ce.oi),
                    _fmt_int(ce.volume),
                    _fmt_iv(ce.iv),
                    _fmt_dec(ce.ltp),
                    _fmt_dec(_get_leg_greeks(ce, "delta")),
                    _fmt_dec(_get_leg_greeks(ce, "theta")),
                    strike_label,
                    _fmt_dec(_get_leg_greeks(pe, "theta")),
                    _fmt_dec(_get_leg_greeks(pe, "delta")),
                    _fmt_dec(pe.ltp),
                    _fmt_iv(pe.iv),
                    _fmt_int(pe.volume),
                    _fmt_int(pe.oi),
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


def show_futures(broker_service, symbol: str, console: Console) -> None:
    """Display futures contract details via domain objects."""
    session = get_session()
    sym = normalize_symbol(symbol)
    exchange = "NFO"
    if any(c in sym for c in ("GOLD", "SILVER", "CRUDE", "NATURAL", "COPPER", "ZINC")):
        exchange = "MCX"

    instrument = session.universe.equity(sym, exchange)
    try:
        chain = instrument.future_chain()
        contracts = chain.contracts if hasattr(chain, 'contracts') else []

        table = Table(title=f"Futures Contracts for {sym}", header_style="bold yellow")
        table.add_column("Expiry", style="bold white")
        table.add_column("Trading Symbol", style="white")
        table.add_column("Security ID", justify="center")
        table.add_column("Lot Size", justify="right")

        if contracts:
            for c in contracts:
                expiry = getattr(c, "expiry", "N/A")
                c_symbol = getattr(c, "symbol", "N/A")
                security_id = getattr(c, "instrument_id", "N/A")
                lot_size = getattr(c, "lot_size", "N/A")
                table.add_row(str(expiry), str(c_symbol), str(security_id), str(lot_size))
        else:
            table.add_row("No contracts found", "-", "-", "-")

        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error fetching futures details: {exc}[/red]")


def show_historical(broker_service, symbol: str, console: Console) -> None:
    """Display historical candles summary and preview via domain objects."""
    from datetime import timedelta

    session = get_session()
    sym = normalize_symbol(symbol)
    exchange = resolve_exchange(sym)
    instrument = session.universe.equity(sym, exchange)

    to_date = date.today()
    from_date = to_date - timedelta(days=10)

    try:
        df = instrument.history(timeframe="1D", start=from_date.isoformat(), end=to_date.isoformat())

        table = Table(
            title=f"Historical Data Preview: {sym}", header_style="bold magenta"
        )
        table.add_column("Timestamp", style="bold white")
        table.add_column("Open", justify="right")
        table.add_column("High", justify="right")
        table.add_column("Low", justify="right")
        table.add_column("Close", justify="right")
        table.add_column("Volume", justify="right")

        if not df.empty:
            for _, row in df.tail(5).iterrows():
                ts_str = (
                    row["timestamp"].strftime("%Y-%m-%d")
                    if hasattr(row["timestamp"], "strftime")
                    else str(row["timestamp"])
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
            console.print(f"Total Rows: [bold cyan]{len(df)}[/bold cyan] candles")
        else:
            table.add_row("No historical data found", "-", "-", "-", "-", "-")
            console.print(table)
    except Exception as exc:
        console.print(f"[red]Error fetching historical data: {exc}[/red]")


def _build_stream_table(symbol: str, rows: list[list[str]]) -> Table:
    """Build a refreshed tick table from the current rows buffer."""
    tbl = Table(title=f"Live WebSocket Stream: {symbol.upper()}", header_style="bold cyan")
    tbl.add_column("Time", style="dim white", min_width=10)
    tbl.add_column("LTP", style="bold green", justify="right", min_width=12)
    tbl.add_column("Open", justify="right")
    tbl.add_column("High", style="green", justify="right")
    tbl.add_column("Low", style="red", justify="right")
    tbl.add_column("Volume", justify="right")
    tbl.add_column("Change", justify="right")
    for r in rows:
        tbl.add_row(*r)
    return tbl


def show_stream(broker_service, symbol: str, console: Console) -> None:
    """Stream live ticks via domain instrument subscription."""
    import threading

    instrument, exchange = _resolve_instrument(symbol)

    console.print(
        f"[yellow]Connecting for [bold]{symbol}[/bold] ({exchange})…  "
        f"Press [bold]Ctrl+C[/bold] to exit.[/yellow]"
    )

    rows: list[list[str]] = []
    lock = threading.Lock()
    tick_count = 0

    def on_tick(_iid, payload) -> None:
        nonlocal tick_count
        try:
            if hasattr(payload, "ltp"):
                ltp = payload.ltp
                open_ = getattr(payload, "open", 0)
                high = getattr(payload, "high", 0)
                low = getattr(payload, "low", 0)
                vol = getattr(payload, "volume", 0)
                chg = getattr(payload, "change_pct", getattr(payload, "change", 0))
                ts = getattr(payload, "event_time", getattr(payload, "timestamp", None))
            elif isinstance(payload, dict):
                ltp = payload.get("last_price", 0)
                open_ = high = low = chg = 0
                vol = 0
                ts = None
            else:
                return

            ts_str = (
                ts.strftime("%H:%M:%S")
                if ts and hasattr(ts, "strftime")
                else datetime.now().strftime("%H:%M:%S")
            )
            chg_str = (
                f"[green]+{float(chg):,.2f}[/green]"
                if float(chg) >= 0
                else f"[red]{float(chg):,.2f}[/red]"
            )

            row = [
                ts_str,
                f"₹{float(ltp):>12,.2f}",
                f"{float(open_):,.2f}",
                f"{float(high):,.2f}",
                f"{float(low):,.2f}",
                f"{int(vol):,}",
                chg_str,
            ]
            with lock:
                rows.append(row)
                if len(rows) > 15:
                    rows.pop(0)
                tick_count += 1
        except Exception as exc:
            logger.debug("tick_processing_failed: %s", exc)

    # Subscribe via domain instrument
    subscription = None
    use_ws = True
    try:
        subscription = instrument.subscribe(on_tick)
    except Exception as exc:
        console.print(
            f"[yellow]Subscription unavailable ({exc}), falling back to REST polling.[/yellow]"
        )
        use_ws = False

    with Live(_build_stream_table(symbol, rows), console=console, refresh_per_second=2) as live:
        try:
            while True:
                time.sleep(0.5)

                if not use_ws:
                    try:
                        q = instrument.refresh()
                        if q is not None:
                            on_tick(None, q)
                    except Exception as exc:
                        logger.debug("rest_polling_failed: %s", exc)

                with lock:
                    current_rows = list(rows)
                tbl = _build_stream_table(symbol, current_rows)
                conn_label = "[green]WS[/green]" if use_ws else "[yellow]REST[/yellow]"
                tbl.caption = f"{conn_label} | Ticks received: [bold]{tick_count}[/bold]"
                live.update(tbl)
        except KeyboardInterrupt:
            pass

    if subscription is not None:
        try:
            subscription.unsubscribe()
        except Exception as exc:
            logger.debug("unsubscribe_cleanup_failed: %s", exc)

    console.print("[yellow]Tick Stream Monitor stopped.[/yellow]")


def run(args: list[str], broker_service, console: Console) -> None:
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
