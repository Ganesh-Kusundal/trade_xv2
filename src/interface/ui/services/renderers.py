"""Shared Rich render helpers for tradex ui broker commands."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from rich.console import Console
from rich.table import Table

from domain.entities import DepthLevel, MarketDepth, Position
from domain.entities.market import QuoteSnapshot
from domain.symbols import normalize_symbol
from interface.ui.utils.time_formatter import format_ist_time


def render_quote(
    console: Console,
    symbol: str,
    quote: QuoteSnapshot,
    *,
    exchange: str | None = None,
) -> None:
    """Render a product ``QuoteSnapshot`` table (event_time / change_pct)."""
    title = f"Quote: {normalize_symbol(symbol)}"
    if exchange:
        title = f"{title} ({exchange})"
    table = Table(title=title, header_style="bold green")
    table.add_column("Metric", style="bold white")
    table.add_column("Value", justify="right")
    table.add_row("LTP", f"\u20b9{quote.ltp:,.2f}")
    table.add_row("Open", f"\u20b9{quote.open:,.2f}")
    table.add_row("High", f"\u20b9{quote.high:,.2f}")
    table.add_row("Low", f"\u20b9{quote.low:,.2f}")
    table.add_row("Prev Close", f"\u20b9{quote.close:,.2f}")
    table.add_row("Change %", f"{quote.change_pct:,.2f}")
    table.add_row("Volume", f"{quote.volume:,}")
    et = quote.event_time
    ts_str = format_ist_time(et) if isinstance(et, datetime) else str(et)
    table.add_row("Last Updated", ts_str)
    console.print(table)


def quote_table(
    symbol: str,
    quote: QuoteSnapshot | None,
    *,
    exchange: str = "",
    title_prefix: str = "Quote Terminal",
) -> Table:
    """Build a quote ``Table`` for Live refresh (product ``QuoteSnapshot`` only)."""
    title = f"{title_prefix}: {symbol.upper()}"
    if exchange:
        title = f"{title} ({exchange})"
    table = Table(title=title, header_style="bold green")
    table.add_column("Metric", style="bold white")
    table.add_column("Value", justify="right")
    if quote is None:
        table.add_row("Status", "[red]No quote data received[/red]")
        return table
    et = quote.event_time
    ts_str = format_ist_time(et) if isinstance(et, datetime) else str(et)
    table.add_row("Last Traded Price (LTP)", f"Rs. {quote.ltp:,.2f}")
    table.add_row("Open", f"Rs. {quote.open:,.2f}")
    table.add_row("High", f"Rs. {quote.high:,.2f}")
    table.add_row("Low", f"Rs. {quote.low:,.2f}")
    table.add_row("Prev Close", f"Rs. {quote.close:,.2f}")
    table.add_row("Change %", f"{quote.change_pct:,.2f}")
    table.add_row("Volume", f"{quote.volume:,}")
    table.add_row("Last Updated", ts_str)
    return table


def render_depth(console: Console, symbol: str, depth_obj: Any) -> None:
    """Render market depth bid/ask table."""
    depth: MarketDepth = depth_obj
    bids: list[DepthLevel] = list(depth.bids) if depth.bids else []
    asks: list[DepthLevel] = list(depth.asks) if depth.asks else []
    table = Table(title=f"Market Depth: {normalize_symbol(symbol)}", header_style="bold magenta")
    table.add_column("Bid Qty", style="green", justify="right")
    table.add_column("Bid Price", style="bold green", justify="right")
    table.add_column("Ask Price", style="bold red", justify="right")
    table.add_column("Ask Qty", style="red", justify="right")
    levels = max(len(bids), len(asks))
    for i in range(levels):
        bid: DepthLevel | None = bids[i] if i < len(bids) else None
        ask: DepthLevel | None = asks[i] if i < len(asks) else None
        table.add_row(
            f"{bid.quantity:,}" if bid else "-",
            f"\u20b9{bid.price:,.2f}" if bid else "-",
            f"\u20b9{ask.price:,.2f}" if ask else "-",
            f"{ask.quantity:,}" if ask else "-",
        )
    console.print(table)


def render_funds(console: Console, funds: Any) -> None:
    """Render account funds / margin summary."""
    table = Table(title="Account Summary", header_style="bold magenta")
    table.add_column("Metric", style="bold white")
    table.add_column("Value", justify="right")

    def _dec(val: Any) -> Decimal:
        return Decimal(str(val or 0))

    sod = _dec(getattr(funds, "sod_limit", None) or getattr(funds, "equity", 0))
    avail = _dec(getattr(funds, "available_balance", None) or getattr(funds, "available_margin", 0))
    utilized = _dec(getattr(funds, "utilized_amount", None) or getattr(funds, "utilized_margin", 0))
    collateral = _dec(getattr(funds, "collateral_amount", 0))
    withdrawable = _dec(getattr(funds, "withdrawable_balance", avail))

    table.add_row("SOD Limit / Equity", f"Rs. {sod:,.2f}")
    table.add_row("Available Balance", f"Rs. {avail:,.2f}")
    table.add_row("Utilized Amount", f"Rs. {utilized:,.2f}")
    table.add_row("Collateral Amount", f"Rs. {collateral:,.2f}")
    table.add_row("Withdrawable Balance", f"Rs. {withdrawable:,.2f}")
    console.print(table)


def render_account_with_pnl(console: Console, funds: Any, positions: list[Any]) -> None:
    """Render funds plus day PnL rollup from positions."""
    render_funds(console, funds)

    realized = sum(Decimal(str(getattr(p, "realized_pnl", 0) or 0)) for p in positions)
    unrealized = sum(Decimal(str(getattr(p, "unrealized_pnl", 0) or 0)) for p in positions)
    total_pnl = realized + unrealized

    table = Table(title="Day PnL", header_style="bold magenta")
    table.add_column("Metric", style="bold white")
    table.add_column("Value", justify="right")

    def colorize_val(val: Decimal) -> str:
        if val > 0:
            return f"[green]Rs. {val:,.2f}[/green]"
        if val < 0:
            return f"[red]Rs. {val:,.2f}[/red]"
        return f"[white]Rs. {val:,.2f}[/white]"

    table.add_row("Realized Day PnL", colorize_val(realized))
    table.add_row("Unrealized Day PnL", colorize_val(unrealized))
    table.add_row("Total Day PnL", colorize_val(total_pnl))
    console.print(table)


def render_holdings(console: Console, holdings: list[Any]) -> None:
    """Render demat holdings table."""
    table = Table(title="Demat Holdings", header_style="bold green")
    table.add_column("Symbol", style="bold white")
    table.add_column("Qty", justify="right")
    table.add_column("Avg Price", justify="right")
    table.add_column("LTP", justify="right")
    table.add_column("PnL", justify="right")

    total_pnl = Decimal("0.00")
    for h in holdings:
        pnl_val = Decimal(str(getattr(h, "pnl", 0) or 0))
        total_pnl += pnl_val
        pnl_style = "green" if pnl_val > 0 else ("red" if pnl_val < 0 else "white")
        table.add_row(
            getattr(h, "symbol", "?"),
            str(getattr(h, "quantity", 0)),
            f"{Decimal(str(getattr(h, 'avg_price', 0))):,.2f}",
            f"{Decimal(str(getattr(h, 'ltp', 0))):,.2f}",
            f"[{pnl_style}]Rs. {pnl_val:,.2f}[/{pnl_style}]",
        )

    pnl_style = "green" if total_pnl > 0 else ("red" if total_pnl < 0 else "white")
    table.add_section()
    table.add_row("Total", "", "", "", f"[{pnl_style}]Rs. {total_pnl:,.2f}[/{pnl_style}]")
    console.print(table)


def render_positions(console: Console, positions: list[Any]) -> None:
    """Render positions grouped by side and product."""
    long_pos = [p for p in positions if getattr(p, "quantity", 0) > 0]
    short_pos = [p for p in positions if getattr(p, "quantity", 0) < 0]
    day_pos = [
        p for p in positions if getattr(getattr(p, "product_type", None), "value", "") == "INTRADAY"
    ]
    overnight_pos = [
        p
        for p in positions
        if getattr(getattr(p, "product_type", None), "value", "") in ("CNC", "MARGIN", "MTF")
    ]

    def render_position_table(title: str, pos_list: list[Position], style: str) -> None:
        table = Table(title=title, header_style=f"bold {style}")
        table.add_column("Symbol", style="bold white")
        table.add_column("Product", justify="center")
        table.add_column("Net Qty", justify="right")
        table.add_column("Avg Price", justify="right")
        table.add_column("LTP", justify="right")
        table.add_column("PnL", justify="right")

        total_pnl = Decimal("0.00")
        for p in pos_list:
            pnl_val = Decimal(str(getattr(p, "unrealized_pnl", 0) or 0)) + Decimal(
                str(getattr(p, "realized_pnl", 0) or 0)
            )
            total_pnl += pnl_val
            pnl_style = "green" if pnl_val > 0 else ("red" if pnl_val < 0 else "white")
            product = getattr(getattr(p, "product_type", None), "value", "?")
            table.add_row(
                getattr(p, "symbol", "?"),
                product,
                str(getattr(p, "quantity", 0)),
                f"{Decimal(str(getattr(p, 'avg_price', 0))):,.2f}",
                f"{Decimal(str(getattr(p, 'ltp', 0))):,.2f}",
                f"[{pnl_style}]Rs. {pnl_val:,.2f}[/{pnl_style}]",
            )
        pnl_style = "green" if total_pnl > 0 else ("red" if total_pnl < 0 else "white")
        table.add_section()
        table.add_row(
            "Total PnL", "", "", "", "", f"[{pnl_style}]Rs. {total_pnl:,.2f}[/{pnl_style}]"
        )
        console.print(table)
        console.print()

    console.print("Positions Overview:")
    console.print()
    render_position_table("Long Positions", long_pos, "green")
    render_position_table("Short Positions", short_pos, "red")
    render_position_table("Day Positions (INTRADAY)", day_pos, "cyan")
    render_position_table("Overnight Positions (CNC/MARGIN)", overnight_pos, "magenta")
