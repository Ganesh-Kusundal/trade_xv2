"""Live-feed smoke command: tradex feed test <segment> <symbol>.

Builds the instrument via the segment resolver, runs the broker-agnostic
:class:`~interface.ui.services.feed_probe.FeedProbe`, and renders a
pass/fail report.  This is the "live feed testing" surface — assert
ticks/depth arrive within a window, no errors, guaranteed teardown.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.table import Table

from interface.ui.commands.segment_resolver import (
    list_segments,
    resolve_instrument,
)
from interface.ui.services.active_session import get_active_session
from interface.ui.services.feed_probe import FeedProbe

if TYPE_CHECKING:
    from domain.universe import Session

logger = logging.getLogger(__name__)


def run(args: list[str], broker_service: Any, console: Console) -> None:
    """Entry point: tradex feed test <segment> <symbol> [--duration 10] [--depth]."""
    if not args or args[0] in ("--help", "-h", "help"):
        _usage(console)
        return

    if args[0] != "test":
        console.print(f"[red]Unknown feed subcommand: {args[0]}[/red]")
        _usage(console)
        return

    rest = args[1:]
    if not rest:
        console.print(
            "[red]Usage: tradex feed test <segment> <symbol> [--duration 10] [--depth][/red]"
        )
        return

    segment = rest[0].lower()
    pos = [a for a in rest[1:] if not a.startswith("--")]
    if not pos:
        console.print("[red]Missing symbol.[/red]")
        return
    symbol = pos[0]

    duration = 10.0
    if "--duration" in rest:
        i = rest.index("--duration")
        if i + 1 < len(rest):
            try:
                duration = float(rest[i + 1])
            except ValueError:
                pass
    depth = "--depth" in rest

    def _flag(name: str) -> str | None:
        if name in rest:
            i = rest.index(name)
            if i + 1 < len(rest):
                return rest[i + 1]
        return None

    expiry = _flag("--expiry")
    strike = _flag("--strike")
    right = _flag("--right")
    exchange = _flag("--exchange")

    session = get_active_session(broker_service)
    try:
        instrument = resolve_instrument(
            session,
            segment,
            symbol,
            expiry=expiry,
            strike=strike,
            right=right,
            exchange=exchange,
        )
    except Exception as exc:
        console.print(f"[red]Resolve failed: {exc}[/red]")
        return

    console.print(
        f"[yellow]Probing live feed for [bold]{symbol}[/bold] ({segment}) "
        f"for {duration:g}s{' + depth' if depth else ''}…[/yellow]"
    )
    result = FeedProbe().run(instrument, duration_s=duration, depth=depth)
    _render(result, console)


def _render(result, console: Console) -> None:
    healthy = result.is_healthy()
    status = "[green]PASS[/green]" if healthy else "[red]FAIL[/red]"
    tbl = Table(
        title=f"Live Feed Smoke: {result.instrument_id}", header_style="bold cyan"
    )
    tbl.add_column("Check", style="bold white")
    tbl.add_column("Result", justify="right")
    tbl.add_row("Health", status)
    tbl.add_row("Ticks", str(result.tick_count))
    tbl.add_row("Depth frames", str(result.depth_count))
    tbl.add_row(
        "First frame latency",
        f"{result.first_frame_latency_s:.2f}s" if result.first_frame_latency_s is not None else "-",
    )
    tbl.add_row("Duration", f"{result.duration_s:g}s")
    console.print(tbl)
    if result.errors:
        console.print("[red]Errors:[/red]")
        for e in result.errors:
            console.print(f"  [red]• {e}[/red]")
    console.print(
        f"{status} — {result.total_frames} frame(s) in {result.duration_s:g}s"
    )


def _usage(console: Console) -> None:
    console.print(
        "[yellow]Usage: tradex feed test <segment> <symbol> "
        "[--duration 10] [--depth] [--expiry YYYY-MM-DD] "
        "[--strike N] [--right CE|PE] [--exchange XXX][/yellow]"
    )
    console.print(f"[dim]Segments: {', '.join(list_segments())}[/dim]")
