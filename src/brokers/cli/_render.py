"""Rich rendering for the broker CLI.

Human-facing output uses Rich tables/panels. Machine output stays JSON:
JSON is emitted when ``--json`` is passed or when stdout is not a TTY
(piped), so scripts, CI, and agents keep getting parseable JSON.
"""

from __future__ import annotations

import json
import logging
import sys
from decimal import Decimal, InvalidOperation
from typing import Any

import yaml
from rich.console import Console

logger = logging.getLogger(__name__)
from rich.table import Table

from brokers.services import safe_serialize

console = Console()


def json_mode(ctx: Any | None = None) -> bool:
    """Return True when output should be raw JSON."""
    if ctx is not None and getattr(ctx, "obj", None) and ctx.obj.get("json"):
        return True
    return not sys.stdout.isatty()


def yaml_mode(ctx: Any | None = None) -> bool:
    """Return True when output should be YAML."""
    return bool(ctx is not None and getattr(ctx, "obj", None) and ctx.obj.get("yaml"))


def quiet_mode(ctx: Any | None = None) -> bool:
    """Return True when output should be suppressed entirely."""
    return bool(ctx is not None and getattr(ctx, "obj", None) and ctx.obj.get("quiet"))


def _fmt(value: Any) -> str:
    if isinstance(value, dict):
        parts: list[str] = []
        for k, v in value.items():
            parts.append(f"{k}={v}")
            if len(parts) >= 4:
                parts.append("…")
                break
        return " ".join(parts)
    if isinstance(value, list):
        if not value:
            return "—"
        if len(value) <= 6:
            return ", ".join(str(x) for x in value)
        return f"[{len(value)} items]"
    return "" if value is None else str(value)


def _render_records(rows: list[dict], title: str | None, out: Console) -> None:
    keys = list(rows[0].keys()) if rows else []
    table = Table(title=title, title_justify="left", show_lines=False)
    for key in keys:
        table.add_column(str(key), style="cyan", overflow="fold")
    for row in rows:
        table.add_row(*(_fmt(row.get(key, "")) for key in keys))
    out.print(table)


def _render_kv(data: dict, title: str | None, out: Console) -> None:
    table = Table(show_header=False, title=title, title_justify="left")
    table.add_column("Key", style="bold cyan", overflow="fold")
    table.add_column("Value", overflow="fold")
    for key, value in data.items():
        table.add_row(str(key), _fmt(value))
    out.print(table)


def _render_quote(data: Any, title: str | None, out: Console) -> None:
    inst = getattr(data, "instrument", None)
    symbol = getattr(inst, "symbol", str(inst) if inst else "—")
    exchange = getattr(inst, "exchange", "—")
    prov = getattr(data, "provenance", None)
    source = getattr(getattr(prov, "source", None), "broker_id", "—") if prov else "—"
    rows = {
        "symbol": symbol,
        "exchange": exchange,
        "ltp": str(getattr(data, "ltp", "")),
        "open": str(getattr(data, "open", "")),
        "high": str(getattr(data, "high", "")),
        "low": str(getattr(data, "low", "")),
        "close": str(getattr(data, "close", "")),
        "bid": str(getattr(data, "bid", "") or "—"),
        "ask": str(getattr(data, "ask", "") or "—"),
        "volume": getattr(data, "volume", 0),
        "change_pct": str(getattr(data, "change_pct", "")),
        "source": source,
        "event_time": getattr(data, "event_time", ""),
    }
    _render_kv(rows, title, out)


def _render_depth(data: Any, title: str | None, out: Console) -> None:
    table = Table(title=title, title_justify="left", show_header=True, header_style="bold")
    table.add_column("Side", style="cyan")
    table.add_column("Level", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Qty", justify="right")
    table.add_column("Orders", justify="right")
    bids = getattr(data, "bids", None) or []
    asks = getattr(data, "asks", None) or []
    for i, level in enumerate(bids[:20], 1):
        table.add_row(
            "bid",
            str(i),
            str(getattr(level, "price", "")),
            str(getattr(level, "quantity", "")),
            str(getattr(level, "orders", "")),
        )
    for i, level in enumerate(asks[:20], 1):
        table.add_row(
            "ask",
            str(i),
            str(getattr(level, "price", "")),
            str(getattr(level, "quantity", "")),
            str(getattr(level, "orders", "")),
        )
    spread_fn = getattr(data, "spread", None)
    spread = spread_fn() if callable(spread_fn) else None
    out.print(table)
    if spread is not None:
        out.print(f"[dim]spread={spread} depth_type={getattr(data, 'depth_type', '')}[/dim]")


def _render_history(data: Any, title: str | None, out: Console) -> None:
    bars = list(getattr(data, "bars", []) or [])
    rows: list[dict] = []
    for bar in bars[-10:]:
        rows.append(
            {
                "time": getattr(bar, "event_time", ""),
                "open": str(getattr(bar, "open", "")),
                "high": str(getattr(bar, "high", "")),
                "low": str(getattr(bar, "low", "")),
                "close": str(getattr(bar, "close", "")),
                "volume": getattr(bar, "volume", 0),
            }
        )
    if rows:
        _render_records(rows, title, out)
    else:
        out.print(f"[dim]{title or 'History'}: no bars[/dim]")
    brokers_fn = getattr(data, "brokers_contributing", None)
    brokers = brokers_fn() if callable(brokers_fn) else set()
    out.print(
        f"[dim]bars={getattr(data, 'bar_count', len(bars))} "
        f"timeframe={getattr(data, 'timeframe', '')} "
        f"brokers={', '.join(sorted(brokers)) or '—'}[/dim]"
    )


def _num_fmt(value: Any, *, max_places: int = 2) -> str:
    """Human price/strike: drop trailing zeros (24200 not 24200.000000)."""
    if value is None:
        return "—"
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    if d == d.to_integral_value():
        return str(int(d))
    text = f"{d:.{max_places}f}".rstrip("0").rstrip(".")
    return text or "0"


def _leg_field(leg: Any, name: str) -> str:
    if leg is None:
        return "—"
    val = leg.get(name) if isinstance(leg, dict) else getattr(leg, name, None)
    if val is None:
        return "—"
    if name in {"oi", "volume"}:
        try:
            return str(int(val))
        except (TypeError, ValueError):
            return str(val)
    if name in {"ltp", "iv", "bid", "ask", "strike"}:
        return _num_fmt(val)
    return str(val)


def _chain_strike_rows(data: Any) -> list[dict]:
    """Normalize OptionChain strikes to dict rows for tabular render."""
    strikes = list(getattr(data, "strikes", None) or [])
    rows: list[dict] = []
    for row in strikes:
        if hasattr(row, "to_dict"):
            rows.append(row.to_dict())
        elif isinstance(row, dict):
            rows.append(row)
        else:
            call = getattr(row, "call", None)
            put = getattr(row, "put", None)
            rows.append(
                {
                    "strike": getattr(row, "strike", None),
                    "call": call.to_dict() if hasattr(call, "to_dict") else call,
                    "put": put.to_dict() if hasattr(put, "to_dict") else put,
                }
            )
    return rows


def _atm_strike_value(data: Any, rows: list[dict]) -> Any:
    atm = getattr(data, "atm", None)
    if atm is not None:
        strike = getattr(atm, "strike", None)
        if strike is not None:
            return strike
    spot = getattr(data, "spot", None)
    if spot is not None and rows:
        try:
            spot_f = float(spot)
            return min(rows, key=lambda r: abs(float(r.get("strike", 0)) - spot_f)).get("strike")
        except (TypeError, ValueError):
            pass
    if rows:
        return rows[len(rows) // 2].get("strike")
    return None


def _atm_window(
    rows: list[dict], atm_strike: Any, *, half: int = 10
) -> tuple[list[dict], int, int]:
    if not rows:
        return [], 0, 0
    idx = len(rows) // 2
    if atm_strike is not None:
        try:
            atm_f = float(atm_strike)
            idx = min(range(len(rows)), key=lambda i: abs(float(rows[i].get("strike", 0)) - atm_f))
        except (TypeError, ValueError):
            pass
    lo = max(0, idx - half)
    hi = min(len(rows), idx + half + 1)
    return rows[lo:hi], lo, hi


def _render_option_chain(data: Any, title: str | None, out: Console) -> None:
    underlying = getattr(data, "underlying", "—")
    exchange = getattr(data, "exchange", "—")
    expiry = str(getattr(data, "expiry", "—"))
    rows = _chain_strike_rows(data)
    atm_strike = _atm_strike_value(data, rows)
    window, lo, hi = _atm_window(rows, atm_strike)

    out.print(
        f"[dim]{underlying} · {exchange} · expiry {expiry} · "
        f"{len(rows)} strikes · atm {_num_fmt(atm_strike) if atm_strike is not None else '—'}[/dim]"
    )

    table = Table(title=title, title_justify="left", show_header=True, header_style="bold")
    table.add_column("CE LTP", justify="right", style="green")
    table.add_column("CE OI", justify="right", style="dim")
    table.add_column("Strike", justify="center", style="bold yellow")
    table.add_column("PE LTP", justify="right", style="red")
    table.add_column("PE OI", justify="right", style="dim")
    if not window:
        table.add_row("—", "—", "no chain data", "—", "—")
    else:
        for row in window:
            call = row.get("call") or {}
            put = row.get("put") or {}
            strike = row.get("strike")
            strike_txt = _num_fmt(strike)
            try:
                if atm_strike is not None and float(strike) == float(atm_strike):
                    strike_txt = f"[bold]{strike_txt}[/bold]"
            except (TypeError, ValueError):
                pass
            table.add_row(
                _leg_field(call, "ltp"),
                _leg_field(call, "oi"),
                strike_txt,
                _leg_field(put, "ltp"),
                _leg_field(put, "oi"),
            )
    out.print(table)
    if len(rows) > len(window):
        out.print(f"[dim]showing strikes {lo + 1}–{hi} of {len(rows)} (ATM ±10)[/dim]")


def _render_capabilities(data: dict, title: str | None, out: Console) -> None:
    _render_kv({"broker_id": data.get("broker_id", "—")}, title, out)
    extensions = data.get("extensions") or []
    if extensions:
        rows = [{"extension": str(ext)} for ext in extensions]
        _render_records(rows, "Extensions", out)
    matrix = data.get("matrix") or {}
    if matrix:
        enabled = {k: v for k, v in matrix.items() if v}
        if enabled:
            _render_kv(enabled, "Capability matrix (enabled)", out)


def _domain_type_name(data: Any) -> str | None:
    """Map domain value objects to their rendering kind via isinstance."""
    from domain.candles.historical import HistoricalSeries
    from domain.entities.market import MarketDepth, QuoteSnapshot

    if isinstance(data, QuoteSnapshot):
        return "QuoteSnapshot"
    if isinstance(data, MarketDepth):
        return "MarketDepth"
    if isinstance(data, HistoricalSeries):
        return "HistoricalSeries"
    # OptionChain has two implementations — check both
    try:
        from domain.options.option_chain import OptionChain as RichOptionChain

        if isinstance(data, RichOptionChain):
            return "OptionChain"
    except ImportError:
        pass
    try:
        from domain.entities.options import OptionChain as V0OptionChain

        if isinstance(data, V0OptionChain):
            return "OptionChain"
    except ImportError:
        pass
    return None


def present(
    ctx: Any | None,
    data: Any,
    *,
    title: str | None = None,
    out: Console | None = None,
) -> None:
    """Render ``data`` as Rich (default), JSON, or YAML (machine modes)."""
    if quiet_mode(ctx):
        return
    target = out or console
    if yaml_mode(ctx):
        logger.info(yaml.safe_dump(safe_serialize(data), default_flow_style=False, sort_keys=False))
        return
    if json_mode(ctx):
        logger.info(json.dumps(safe_serialize(data), default=str, indent=2))
        return

    kind = _domain_type_name(data)
    if kind == "QuoteSnapshot":
        _render_quote(data, title, target)
        return
    if kind == "MarketDepth":
        _render_depth(data, title, target)
        return
    if kind == "HistoricalSeries":
        _render_history(data, title, target)
        return
    if kind == "OptionChain":
        _render_option_chain(data, title, target)
        return

    if isinstance(data, dict) and "extensions" in data and "broker_id" in data:
        _render_capabilities(data, title, target)
        return

    if isinstance(data, list) and data and all(isinstance(x, str) for x in data):
        _render_records([{"broker": b} for b in data], title, target)
        return

    serial = safe_serialize(data)
    if isinstance(serial, list) and serial and all(isinstance(r, dict) for r in serial):
        _render_records(serial, title, target)
    elif isinstance(serial, dict):
        _render_kv(serial, title, target)
    elif serial is None:
        target.print("[dim](no data)[/dim]")
    else:
        target.print(str(serial))
