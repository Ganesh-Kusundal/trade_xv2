"""OOP-by-segment data CLI.

Routes ``tradex asset <segment> <symbol> [action]`` through the
resolved domain :class:`~domain.instruments.instrument.Instrument` and
``Session.data`` — never the raw gateway.  Broker-agnostic: the same
code drives Dhan, Upstox, or Paper via the ``DataProvider`` protocol.

Examples::

    tradex asset equity RELIANCE quote
    tradex asset equity RELIANCE history --tf 1D --days 30
    tradex asset index  NIFTY   depth
    tradex asset options NIFTY chain --expiry 2026-07-30
    tradex asset futures NIFTY contracts
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.table import Table

from domain.instruments.asset_kind import AssetKind
from interface.ui.commands.segment_resolver import (
    list_segments,
    resolve_instrument,
)
from interface.ui.services.active_session import get_active_session

if TYPE_CHECKING:
    from domain.universe import Session

logger = logging.getLogger(__name__)

_ACTIONS = {"quote", "history", "depth", "chain"}


def run(args: list[str], broker_service: Any, console: Console) -> None:
    """Entry point: tradex asset <segment> <symbol> [action] [--flags]."""
    if not args:
        _usage(console)
        return

    segment = args[0].lower()
    rest = args[1:]

    expiry = _flag(rest, "--expiry")
    strike = _flag(rest, "--strike")
    right = _flag(rest, "--right")
    exchange = _flag(rest, "--exchange")
    tf = _flag(rest, "--tf") or "1D"
    days_s = _flag(rest, "--days")
    frm = _flag(rest, "--from")
    to = _flag(rest, "--to")

    pos = [a for a in rest if not a.startswith("--") and a not in _flag_values(rest)]
    if not pos:
        console.print("[red]Missing symbol.[/red]")
        _usage(console)
        return
    symbol = pos[0]
    action = pos[1] if len(pos) > 1 and pos[1] in _ACTIONS else "quote"

    session = get_active_session(broker_service)
    try:
        instrument = resolve_instrument(
            session,
            segment,
            symbol,
            expiry=_coerce_date(expiry) if expiry else None,
            strike=Decimal(strike) if strike else None,
            right=right,
            exchange=exchange,
        )
    except Exception as exc:
        console.print(f"[red]Resolve failed: {exc}[/red]")
        return

    try:
        if action == "quote":
            _show_quote(instrument, console)
        elif action == "depth":
            _show_depth(instrument, console)
        elif action == "history":
            _show_history(instrument, console, tf, int(days_s) if days_s else 120, frm, to)
        elif action == "chain":
            _show_chain(instrument, console, expiry)
    except Exception as exc:
        logger.exception("asset_%s_failed", action)
        console.print(f"[red]{action} failed: {exc}[/red]")


# ── flag helpers ──────────────────────────────────────────────────────────


def _flag(tokens: list[str], name: str) -> str | None:
    if name in tokens:
        i = tokens.index(name)
        if i + 1 < len(tokens):
            return tokens[i + 1]
    return None


def _flag_values(tokens: list[str]) -> set[str]:
    vals: set[str] = set()
    for i, t in enumerate(tokens):
        if t.startswith("--") and i + 1 < len(tokens):
            vals.add(tokens[i + 1])
    return vals


def _coerce_date(v: str | None):
    if v is None:
        return None
    from datetime import datetime

    s = v.strip()
    if "-" in s:
        return datetime.strptime(s, "%Y-%m-%d").date()
    return datetime.strptime(s, "%Y%m%d").date()


def _usage(console: Console) -> None:
    console.print(
        "[yellow]Usage: tradex asset <segment> <symbol> [action] "
        "[--tf 1D] [--days 120] [--from ..] [--to ..] "
        "[--expiry YYYY-MM-DD] [--strike 25000] [--right CE] [--exchange NSE][/yellow]"
    )
    console.print(
        f"[dim]Segments: {', '.join(list_segments())} | "
        f"Actions: {', '.join(sorted(_ACTIONS))}[/dim]"
    )


# ── renderers ──────────────────────────────────────────────────────────────


def _show_quote(instrument, console: Console) -> None:
    q = instrument.refresh()
    if q is None:
        console.print("[red]No quote data.[/red]")
        return
    tbl = Table(
        title=f"Quote: {instrument.symbol} ({instrument.exchange})",
        header_style="bold green",
    )
    tbl.add_column("Metric", style="bold white")
    tbl.add_column("Value", justify="right")
    tbl.add_row("LTP", f"₹{_f(q.ltp)}")
    tbl.add_row("Open", f"₹{_f(q.open)}")
    tbl.add_row("High", f"₹{_f(q.high)}")
    tbl.add_row("Low", f"₹{_f(q.low)}")
    tbl.add_row("Prev Close", f"₹{_f(q.close)}")
    chg = getattr(q, "change_pct", None)
    tbl.add_row("Change %", _f(chg) if chg is not None else "-")
    tbl.add_row("Volume", f"{int(q.volume):,}")
    console.print(tbl)


def _show_depth(instrument, console: Console) -> None:
    d = instrument.depth()
    if d is None or not (d.bids or d.asks):
        console.print("[red]No depth data.[/red]")
        return
    tbl = Table(
        title=f"Market Depth: {instrument.symbol}", header_style="bold magenta"
    )
    tbl.add_column("Bid Qty", style="green", justify="right")
    tbl.add_column("Bid", style="bold green", justify="right")
    tbl.add_column("Ask", style="bold red", justify="right")
    tbl.add_column("Ask Qty", style="red", justify="right")
    levels = max(len(d.bids), len(d.asks))
    for i in range(min(levels, 5)):
        bid = d.bids[i] if i < len(d.bids) else None
        ask = d.asks[i] if i < len(d.asks) else None
        tbl.add_row(
            f"{int(bid.quantity):,}" if bid else "-",
            f"₹{_f(bid.price)}" if bid else "-",
            f"₹{_f(ask.price)}" if ask else "-",
            f"{int(ask.quantity):,}" if ask else "-",
        )
    console.print(tbl)


def _show_history(instrument, console: Console, tf: str, days: int, frm, to) -> None:
    series = instrument.history(timeframe=tf, days=days, start=frm, end=to)
    bars = series.bars if series is not None else []
    if not bars:
        console.print("[red]No historical data.[/red]")
        return
    tbl = Table(
        title=f"History: {instrument.symbol} ({tf})", header_style="bold magenta"
    )
    for c in ("Timestamp", "Open", "High", "Low", "Close", "Volume"):
        tbl.add_column(c, **({} if c == "Timestamp" else {"justify": "right"}))
    for b in bars[-5:]:
        ts = b.event_time
        ts_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)
        tbl.add_row(ts_str, _f(b.open), _f(b.high), _f(b.low), _f(b.close), f"{int(b.volume):,}")
    console.print(tbl)
    console.print(f"[dim]{len(bars)} bars total[/dim]")


def _show_chain(instrument, console: Console, expiry: str | None) -> None:
    kind = instrument.asset_type
    try:
        if kind in (AssetKind.FUTURES.value, AssetKind.COMMODITY.value) or instrument.id.right == "FUT":
            _render_future_chain(instrument.future_chain(), console)
        else:
            chain = instrument.option_chain(expiry=_coerce_date(expiry) if expiry else None)
            _render_option_chain(chain, console)
    except Exception as exc:
        console.print(f"[red]Chain failed: {exc}[/red]")


def _render_option_chain(chain, console: Console) -> None:
    strikes = _chain_strikes(chain)
    tbl = Table(
        title=f"Option Chain {getattr(chain, 'underlying', '')} {getattr(chain, 'expiry', '')}",
        header_style="bold cyan",
    )
    tbl.add_column("CE LTP", style="bold green", justify="right")
    tbl.add_column("Strike", style="bold yellow", justify="center")
    tbl.add_column("PE LTP", style="bold red", justify="right")
    if not strikes:
        tbl.add_row("-", "No chain data", "-")
    for s in strikes:
        ce = s.get("call") or {}
        pe = s.get("put") or {}
        tbl.add_row(_f(ce.get("ltp")), _f(s.get("strike")), _f(pe.get("ltp")))
    console.print(tbl)


def _render_future_chain(chain, console: Console) -> None:
    contracts = getattr(chain, "contracts", ()) or ()
    tbl = Table(
        title=f"Futures: {getattr(chain, 'underlying', '')}", header_style="bold yellow"
    )
    tbl.add_column("Expiry", style="bold white")
    tbl.add_column("Symbol", style="white")
    tbl.add_column("LTP", justify="right")
    tbl.add_column("Lot", justify="right")
    if not contracts:
        tbl.add_row("No contracts", "-", "-", "-")
    for c in contracts:
        tbl.add_row(
            str(getattr(c, "expiry", "-")),
            str(getattr(c, "symbol", "-")),
            _f(getattr(c, "ltp", None)),
            str(getattr(c, "lot_size", "-")),
        )
    console.print(tbl)


def _chain_strikes(chain) -> list[dict]:
    rows = getattr(chain, "strikes", None)
    if not rows:
        return []
    out: list[dict] = []
    for r in rows:
        if hasattr(r, "to_dict"):
            out.append(r.to_dict())
        elif isinstance(r, dict):
            out.append(r)
        else:
            out.append(
                {
                    "strike": getattr(r, "strike", None),
                    "call": getattr(r, "call", {}) or {},
                    "put": getattr(r, "put", {}) or {},
                }
            )
    return out


def _f(v) -> str:
    if v is None:
        return "-"
    try:
        return f"{float(v):,.2f}"
    except (ValueError, TypeError):
        return str(v)
