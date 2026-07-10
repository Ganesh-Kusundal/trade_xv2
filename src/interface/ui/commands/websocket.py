"""CLI command handler for WebSocket diagnostics.

Shows real connection status for the Dhan market feed and order stream
by inspecting the live BrokerService / LifecycleManager rather than
generating fake random values.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.table import Table

from interface.ui.services.broker_service import BrokerService

logger = logging.getLogger(__name__)


def _ws_status(broker_service: BrokerService) -> dict[str, Any]:
    """Collect real WebSocket / lifecycle metrics from the BrokerService."""
    stats: dict[str, Any] = {
        "market_feed_connected": False,
        "order_stream_connected": False,
        "reconnect_count": 0,
        "tick_count": 0,
        "last_tick_age_s": None,
        "token_refresh_count": 0,
        "token_last_error": False,
        "lifecycle_services": 0,
        "broker_name": broker_service.active_broker_name.upper(),
    }

    # Dhan gateway internals
    gw = getattr(broker_service, "_gateway", None)
    conn = getattr(gw, "_conn", None) if gw else None

    if conn is not None:
        # Market feed
        mf = getattr(conn, "market_feed", None)
        if mf is not None:
            stats["market_feed_connected"] = bool(getattr(mf, "is_connected", False))
            stats["reconnect_count"] = int(getattr(mf, "_reconnect_count", 0))
            lt = getattr(mf, "_last_tick_time", None)
            if lt is not None:
                try:
                    age = (datetime.now() - lt).total_seconds()
                    stats["last_tick_age_s"] = round(age, 1)
                except Exception as exc:
                    logger.debug("tick_age_calc_failed: %s", exc)
            stats["tick_count"] = int(getattr(mf, "_tick_count", 0))

        # Order stream
        os_ = getattr(conn, "order_stream", None)
        if os_ is not None:
            stats["order_stream_connected"] = bool(getattr(os_, "is_connected", False))

        # Token scheduler
        sched = getattr(conn, "_token_scheduler", None)
        if sched is not None:
            stats["token_refresh_count"] = int(getattr(sched, "refresh_count", 0))
            stats["token_last_error"] = bool(getattr(sched, "_last_error", None))

    # Upstox gateway
    upstox_gw = getattr(broker_service, "_upstox_gateway", None)
    if upstox_gw is not None:
        ws = getattr(getattr(upstox_gw, "_broker", None), "market_data_websocket", None)
        if ws is not None:
            stats["upstox_ws_connected"] = bool(getattr(ws, "is_connected", False))
            subs = getattr(ws, "_subscribed", set())
            stats["upstox_subscriptions"] = len(subs)

    # LifecycleManager service count
    lc = getattr(broker_service, "_lifecycle", None)
    if lc is not None:
        svcs = getattr(lc, "_services", [])
        stats["lifecycle_services"] = len(svcs)

    return stats


def _build_ws_table(stats: dict[str, Any], elapsed: int) -> Table:
    """Build the diagnostics table from real stats."""

    def _conn(val: bool) -> str:
        return "[green]CONNECTED[/green]" if val else "[red]DISCONNECTED[/red]"

    table = Table(
        title=f"WebSocket Diagnostics — {stats['broker_name']} (running {elapsed}s)",
        header_style="bold blue",
    )
    table.add_column("Metric", style="bold white", min_width=30)
    table.add_column("Value", justify="center", min_width=20)

    table.add_row("Dhan Market Feed", _conn(stats["market_feed_connected"]))
    table.add_row("Dhan Order Stream", _conn(stats["order_stream_connected"]))

    if "upstox_ws_connected" in stats:
        table.add_row("Upstox WebSocket", _conn(stats["upstox_ws_connected"]))
        table.add_row("Upstox Subscriptions", str(stats["upstox_subscriptions"]))

    reconnects = stats["reconnect_count"]
    table.add_row(
        "Reconnect Count",
        f"[yellow]{reconnects}[/yellow]" if reconnects > 0 else "0",
    )
    table.add_row("Ticks Received", f"{stats['tick_count']:,}")

    age = stats.get("last_tick_age_s")
    if age is not None:
        age_label = f"{age:.1f}s ago"
        color = "red" if age > 10 else "green"
        table.add_row("Last Tick Age", f"[{color}]{age_label}[/{color}]")
    else:
        table.add_row("Last Tick Age", "[dim]no data yet[/dim]")

    table.add_row("Token Refresh Count", str(stats["token_refresh_count"]))
    table.add_row(
        "Token Last Error",
        "[red]YES[/red]" if stats["token_last_error"] else "[green]None[/green]",
    )
    table.add_row("Lifecycle Services", str(stats["lifecycle_services"]))

    return table


def run(args: list[str], broker_service: BrokerService, console: Console) -> None:
    """Entry point for websocket diagnostics subcommand.

    Streams real connection metrics until Ctrl+C.  Pass ``--once`` to
    print a single snapshot and exit (useful for scripting).
    """
    once = "--once" in args

    if once:
        stats = _ws_status(broker_service)
        console.print(_build_ws_table(stats, 0))
        return

    console.print(
        "[yellow]Starting WebSocket Diagnostics. Press [bold]Ctrl+C[/bold] to stop…[/yellow]"
    )

    start = time.time()
    initial_stats = _ws_status(broker_service)

    with Live(
        _build_ws_table(initial_stats, 0),
        console=console,
        refresh_per_second=1,
    ) as live:
        try:
            while True:
                time.sleep(1)
                elapsed = int(time.time() - start)
                stats = _ws_status(broker_service)
                live.update(_build_ws_table(stats, elapsed))
        except KeyboardInterrupt:
            pass

    console.print("[yellow]WebSocket diagnostics stopped.[/yellow]")
