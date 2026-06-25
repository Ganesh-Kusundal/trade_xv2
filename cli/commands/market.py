"""CLI command handler for market data operations."""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta

from rich.console import Console
from rich.live import Live
from rich.table import Table

from cli.services.broker_service import BrokerService

logger = logging.getLogger(__name__)

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
        quote = gw.quote(symbol, exchange)
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
        depth = gw.depth(symbol, exchange)
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
        except Exception as exc:
            logger.debug("expiry_fetch_failed: %s: %s", sym, exc)

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
        if hasattr(chain, "to_dict"):
            chain = chain.to_dict()

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
                atm_dist = min((abs(float(s["strike"]) - float(spot)) for s in strikes), default=0)
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


def show_futures(broker_service: BrokerService, symbol: str, console: Console) -> None:
    """Display futures contract details."""
    gw = broker_service.active_broker
    sym = symbol.upper().strip()
    exchange = "NFO"
    # Commodities route to MCX
    if any(c in sym for c in ("GOLD", "SILVER", "CRUDE", "NATURAL", "COPPER", "ZINC")):
        exchange = "MCX"

    try:
        chain = gw.future_chain(sym, exchange)
        contracts = chain.contracts if hasattr(chain, 'contracts') else []

        table = Table(title=f"Futures Contracts for {sym}", header_style="bold yellow")
        table.add_column("Expiry", style="bold white")
        table.add_column("Trading Symbol", style="white")
        table.add_column("Security ID", justify="center")
        table.add_column("Lot Size", justify="right")

        if contracts:
            for c in contracts:
                expiry = c.expiry if hasattr(c, 'expiry') else (c.get("expiry", "N/A") if hasattr(c, 'get') else "N/A")
                # P-2.3: Fixed - use c_symbol instead of shadowing function parameter
                c_symbol = c.symbol if hasattr(c, 'symbol') else (c.get("symbol", "N/A") if hasattr(c, 'get') else "N/A")
                security_id = c.security_id if hasattr(c, 'security_id') else (c.get("security_id", "N/A") if hasattr(c, 'get') else "N/A")
                lot_size = c.lot_size if hasattr(c, 'lot_size') else (c.get("lot_size", "N/A") if hasattr(c, 'get') else "N/A")
                table.add_row(
                    str(expiry),
                    str(c_symbol),
                    str(security_id),
                    str(lot_size),
                )
        else:
            table.add_row("No contracts found", "-", "-", "-")

        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error fetching futures details: {exc}[/red]")


def show_historical(broker_service: BrokerService, symbol: str, console: Console) -> None:
    """Display historical candles summary and preview via MarketDataComposer."""
    from cli.composer_helpers import get_market_data_composer
    from brokers.common.async_compat import run_async_compat
    from brokers.common.historical_coordinator import HistoricalQuery
    from domain.historical import InstrumentRef

    # Get MarketDataComposer (lazy-loaded, cached)
    try:
        composer = get_market_data_composer()
    except Exception as exc:
        console.print(f"[red]Failed to initialize MarketDataComposer: {exc}[/red]")
        return

    exchange = resolve_exchange(symbol)
    to_date = date.today()
    from_date = to_date - timedelta(days=10)

    try:
        # Build HistoricalQuery for composer
        query = HistoricalQuery(
            instrument=InstrumentRef(symbol=symbol, exchange=exchange),
            timeframe="1D",
            from_date=from_date,
            to_date=to_date,
        )

        # Execute via composer (async -> sync bridge)
        series, ledger = run_async_compat(
            composer.fetch_historical(query),
            fire_and_forget=False,
        )

        table = Table(
            title=f"Historical Data Preview: {symbol.upper()}", header_style="bold magenta"
        )
        table.add_column("Timestamp", style="bold white")
        table.add_column("Open", justify="right")
        table.add_column("High", justify="right")
        table.add_column("Low", justify="right")
        table.add_column("Close", justify="right")
        table.add_column("Volume", justify="right")

        if series and series.bars:
            # Show last 5 bars
            for bar in series.bars[-5:]:
                ts_str = (
                    bar.timestamp.strftime("%Y-%m-%d")
                    if hasattr(bar.timestamp, "strftime")
                    else str(bar.timestamp)
                )
                table.add_row(
                    ts_str,
                    f"{bar.open:,.2f}",
                    f"{bar.high:,.2f}",
                    f"{bar.low:,.2f}",
                    f"{bar.close:,.2f}",
                    f"{int(bar.volume):,}",
                )
            console.print(table)
            console.print()

            first_ts = series.bars[0].timestamp
            last_ts = series.bars[-1].timestamp
            first_str = (
                first_ts.strftime("%Y-%m-%d")
                if hasattr(first_ts, "strftime")
                else str(first_ts)
            )
            last_str = (
                last_ts.strftime("%Y-%m-%d")
                if hasattr(last_ts, "strftime")
                else str(last_ts)
            )
            degraded_note = " [yellow](degraded)[/yellow]" if series.is_degraded else ""
            console.print(
                f"Total Rows: [bold cyan]{series.bar_count}[/bold cyan]{degraded_note} candles | First: {first_str} | Last: {last_str}"
            )
            if ledger.conflicts:
                console.print(f"[dim]Data conflicts resolved: {len(ledger.conflicts)}[/dim]")
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


def show_stream(broker_service: BrokerService, symbol: str, console: Console) -> None:
    """Stream live ticks via the broker WebSocket and display as a rolling table.

    Uses ``gateway.stream()`` which subscribes to the broker WebSocket and
    fires ``on_tick(quote: Quote)`` for every incoming tick.  The canonical
    ``Quote`` object is broker-agnostic — no security IDs or instrument keys
    are exposed here.

    Falls back to polling REST quotes if the gateway does not support
    ``stream()`` (e.g. MockBroker).
    """
    import threading

    gw = broker_service.active_broker
    exchange = resolve_exchange(symbol)

    console.print(
        f"[yellow]Connecting WebSocket for [bold]{symbol}[/bold] ({exchange})…  "
        f"Press [bold]Ctrl+C[/bold] to exit.[/yellow]"
    )

    rows: list[list[str]] = []
    lock = threading.Lock()
    tick_count = 0

    def on_tick(quote: object) -> None:
        nonlocal tick_count
        # Accept canonical Quote OR raw dict (fallback path)
        try:
            if hasattr(quote, "ltp"):
                ltp = quote.ltp  # type: ignore[attr-defined]
                open_ = quote.open  # type: ignore[attr-defined]
                high = quote.high  # type: ignore[attr-defined]
                low = quote.low  # type: ignore[attr-defined]
                vol = quote.volume  # type: ignore[attr-defined]
                chg = quote.change  # type: ignore[attr-defined]
                ts = quote.timestamp  # type: ignore[attr-defined]
            elif isinstance(quote, dict):
                payload = quote.get("payload", quote)
                ltp = payload.get("last_price", 0) if isinstance(payload, dict) else 0
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

    # Subscribe via the canonical gateway.stream() interface
    ws_handle = None
    use_ws = hasattr(gw, "stream")
    if use_ws:
        try:
            ws_handle = gw.stream(symbol, exchange=exchange, mode="LTP", on_tick=on_tick)
        except Exception as exc:
            console.print(
                f"[yellow]WebSocket unavailable ({exc}), falling back to REST polling.[/yellow]"
            )
            use_ws = False

    with Live(_build_stream_table(symbol, rows), console=console, refresh_per_second=2) as live:
        try:
            while True:
                time.sleep(0.5)

                # Fallback: REST polling when WS is not available
                if not use_ws:
                    try:
                        quote = gw.quote(symbol, exchange)
                        if quote is not None:
                            on_tick(quote)
                    except Exception as exc:
                        logger.debug("rest_polling_failed: %s", exc)

                with lock:
                    current_rows = list(rows)
                tbl = _build_stream_table(symbol, current_rows)
                # Append a footer showing tick count + connection type
                conn_label = "[green]WS[/green]" if use_ws else "[yellow]REST[/yellow]"
                tbl.caption = f"{conn_label} | Ticks received: [bold]{tick_count}[/bold]"
                live.update(tbl)
        except KeyboardInterrupt:
            pass

    # P0 Fix: Clean up via gateway.unstream() instead of direct SDK unsubscribe
    # This ensures _stream_registry, _last_tick_time, and callbacks are properly cleaned
    if ws_handle is not None:
        try:
            gw.unstream(symbol, exchange=exchange, on_tick=on_tick)
        except Exception as exc:
            logger.debug("unstream_cleanup_failed: %s", exc)

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
